"""
RAG（検索して答える仕組み）用のモジュール。

このファイルの役割：
- static/polytech.pdf を読み込み、細かく分割して「ベクターストア」に保存する
- 質問に関係する部分だけを取り出す「Retriever（検索係）」を用意する
- AIとの会話履歴を、あとで見返せるように別のベクターストアに保存する

main.py 側は、ここで用意した関数を呼び出すだけで使えます。
PDF全文を毎回AIに渡すのをやめ、質問に関係する箇所だけを渡すのが目的です。
"""

import os
import threading

import fitz  # PyMuPDF（PDFから文字を取り出すのに使用。既存の依存関係を再利用）
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# -------------------------
# 設定
# -------------------------
# 埋め込み（文章を数値ベクトルに変換）に使う軽量・低コストなモデル。
EMBEDDING_MODEL = "text-embedding-3-small"

# ベクターストアのコレクション名（PDF用・会話履歴用で分ける）。
PDF_COLLECTION = "polytech"
CONVERSATION_COLLECTION = "conversations"

# チャンク（分割された文章のかたまり）のサイズ設定。
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# -------------------------
# 内部キャッシュ
# -------------------------
# 一度作ったRetrieverやベクターストアはメモリにキャッシュしてAPI呼び出しを減らす。
# 複数リクエストが同時に来ても二重に作らないようロックで守る。
_pdf_retriever = None
_pdf_lock = threading.Lock()

_conversation_store = None
_conversation_lock = threading.Lock()


def _persist_dir(root_path, name):
    """ベクターストアの保存先フォルダのパスを返す（app.root_path 基準）。"""
    return os.path.join(root_path, "vectorstores", name)


def _make_embeddings():
    """OpenAIの埋め込みモデルを返す。OPENAI_API_KEY は環境変数から読まれる。"""
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def _extract_pdf_documents(pdf_path):
    """PDFを1ページずつ読み込み、ページ番号付きの Document のリストにする。"""
    doc = fitz.open(pdf_path)
    documents = []
    try:
        for index, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                documents.append(
                    Document(
                        page_content=text,
                        metadata={"source": "polytech.pdf", "page": index + 1},
                    )
                )
    finally:
        doc.close()
    return documents


def _build_or_load_pdf_store(root_path):
    """
    polytech.pdf 用のベクターストアを用意する。
    - すでに保存済みならそれを読み込んで再利用する
    - まだ無ければPDFを分割・ベクトル化して新しく作成し、フォルダに保存する
    """
    persist_dir = _persist_dir(root_path, PDF_COLLECTION)
    embeddings = _make_embeddings()

    # すでに保存済み（フォルダが存在し中身がある）なら読み込んで再利用。
    if os.path.isdir(persist_dir) and os.listdir(persist_dir):
        store = Chroma(
            collection_name=PDF_COLLECTION,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )
        try:
            has_data = store._collection.count() > 0
        except Exception:
            has_data = False
        if has_data:
            return store

    # 無ければ新規作成。
    os.makedirs(persist_dir, exist_ok=True)
    pdf_path = os.path.join(root_path, "static", "polytech.pdf")
    raw_documents = _extract_pdf_documents(pdf_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(raw_documents)

    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=PDF_COLLECTION,
        persist_directory=persist_dir,
    )


def get_pdf_retriever(root_path, k=4):
    """
    polytech.pdf 用の Retriever（検索係）を返す。
    初回だけベクターストアを作成/読み込みし、以降はキャッシュを使い回す。
    """
    global _pdf_retriever
    if _pdf_retriever is not None:
        return _pdf_retriever

    with _pdf_lock:
        if _pdf_retriever is None:
            store = _build_or_load_pdf_store(root_path)
            _pdf_retriever = store.as_retriever(search_kwargs={"k": k})
    return _pdf_retriever


def retrieve_pdf_context(root_path, question, k=4):
    """
    質問に関係するPDFの箇所だけを取り出し、
    (プロンプト用テキスト, 保存用テキスト) のタプルで返す。

    失敗しても例外を投げず、空文字を返す（住民向け画面にエラーを出さないため）。
    """
    try:
        retriever = get_pdf_retriever(root_path, k=k)
        docs = retriever.invoke(question)
    except Exception:
        return "", ""

    if not docs:
        return "", ""

    parts = []
    for doc in docs:
        page = doc.metadata.get("page", "?")
        parts.append(f"[polytech.pdf p.{page}]\n{doc.page_content.strip()}")

    joined = "\n\n---\n\n".join(parts)
    # プロンプト用も保存用も同じ内容を使う。
    return joined, joined


# -------------------------
# 会話履歴用ベクターストア（保存のみ・回答の根拠には使わない）
# -------------------------
def _get_conversation_store(root_path):
    """会話履歴保存用のベクターストアを用意して返す（キャッシュあり）。"""
    global _conversation_store
    if _conversation_store is not None:
        return _conversation_store

    with _conversation_lock:
        if _conversation_store is None:
            persist_dir = _persist_dir(root_path, CONVERSATION_COLLECTION)
            os.makedirs(persist_dir, exist_ok=True)
            _conversation_store = Chroma(
                collection_name=CONVERSATION_COLLECTION,
                embedding_function=_make_embeddings(),
                persist_directory=persist_dir,
            )
    return _conversation_store


def save_conversation(root_path, log_id, question, answer, lang, created_at):
    """
    会話履歴（質問と回答）を会話用ベクターストアに保存する。
    これはあくまで「あとから管理者が確認する」ための保管であり、
    みずほの回答の根拠には使わない。失敗しても例外は投げない。
    """
    try:
        store = _get_conversation_store(root_path)
        content = f"質問: {question}\n回答: {answer}"
        store.add_texts(
            texts=[content],
            metadatas=[
                {
                    "log_id": log_id,
                    "lang": lang,
                    "created_at": created_at,
                }
            ],
        )
        return True
    except Exception:
        return False
