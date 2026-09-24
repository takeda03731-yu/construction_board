import hmac
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, ForeignKey
from openai import OpenAI
from zoneinfo import ZoneInfo

import rag  # PDFの検索（Retriever）と会話履歴の保存を担当する自作モジュール

load_dotenv()



client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------
# AI利用の安全対策の設定
# -------------------------
# 公開掲示板のため、極端に長い質問でAPI料金が増えるのを防ぐ。
MAX_QUESTION_LENGTH = 300   # 住民からの質問の最大文字数
MAX_OUTPUT_TOKENS = 400     # OpenAI APIの回答トークン上限

app = Flask(__name__)

# -------------------------
# 基本設定
# -------------------------
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "SECRET_KEY が設定されていません。"
        "セッションやCSRF保護に使う秘密鍵を環境変数に設定してください。"
    )

# セッションCookieの堅牢性を明示的に設定（Flaskのデフォルト値を明記する）。
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# CSRFトークンによるフォーム保護（全POSTフォームに csrf_token を埋め込む）。
csrf = CSRFProtect(app)

# /ask_ai の連投によるOpenAI APIコスト増加を防ぐ（IP単位のレート制限）。
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[])

# PostgreSQL の接続先を環境変数から取得
# 例:
# postgresql+psycopg://user:password@host:5432/dbname
database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError(
        "DATABASE_URL が設定されていません。"
        "PostgreSQL の接続URLを環境変数に設定してください。"
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 管理者用削除パスワード
ADMIN_DELETE_PASSWORD = os.getenv("ADMIN_DELETE_PASSWORD")


# -------------------------
# DB設定
# -------------------------
class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)


class Comment(db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id"),
        nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)

    replies: Mapped[list["Comment"]] = relationship(
        "Comment",
        backref="parent",
        remote_side=[id]
    )

    def is_reply(self) -> bool:
        return self.parent_id is not None


class AiLog(db.Model):
    """みずほAIへの質問と回答の履歴。あとから管理者が確認するために保存する。"""

    __tablename__ = "ai_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False, default="ja")
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    # Retrieverが取り出したPDFの関連チャンク（根拠として何を参照したかの記録）
    pdf_chunks: Mapped[str | None] = mapped_column(Text, nullable=True)


with app.app_context():
    db.create_all()


# -------------------------
# 表示用固定データ
# -------------------------
SITE_INFO = {
    "construction_name": "令和7年度 管路更新（耐震化）事業 土与丸（是石）地区ほか\n配水管布設替工事掲示板 9月24日現在",
    "image_file": "撤去・連絡工.pdf",  # staticフォルダ内のファイル名
    "image_file2": "工事概要.pdf",
    "image_file3": "臨時駐車場.pdf",
    "image_file4": "ゴミの移動.pdf",
    "image_description": "平素より、本工事に対しまして、地域の皆様にはご理解とご協力をいただき、誠にありがとうございます。本日は、断水にご協力いただきました対象の事業者様および宅地の皆様には、ご迷惑をおかけいたしました。おかげさまで、不要になった仕切弁を撤去することができました。改めてお礼申し上げます。\n\n明日9月25日は、図に示す2箇所において、既設管の撤去工および閉栓工を実施する予定です。当日は朝から南側の箇所に着手し、作業完了後に埋戻しを行います。その後、北側の箇所へ移動して作業を進める予定です。\n\n工事に伴う交通規制につきましては、線路付近の規制範囲内で実施いたします。北側・南側のいずれの方向からも通り抜けができませんので、付近を通行される際は迂回路をご利用くださいますようお願いいたします。\n\n工事箇所周辺には、皆様の安全な通行を確保するため、交通誘導員を配置いたします。通行の際は、現地の案内看板および交通誘導員の指示に従っていただきますようお願いいたします。\n\n今後は、最終工程となる本舗装工事を実施し、本工事を完了する予定でございます。\n\n地域の皆様には、工事や交通規制により引き続きご不便をおかけいたしますが、安全を最優先に作業を進めてまいりますので、工事完了まで何卒ご理解とご協力を賜りますよう、お願い申し上げます。",
    "image_description2": "工事は舗装版切断工から始まり、本舗装復旧工をもって終了となります。\n\n給水分岐替工の際には、個別に断水が発生いたします。断水の際は事前にお知らせいたしますので、ご理解とご協力をお願いいたします。",
    "image_description3": "このたび、近隣の住民様のご厚意により、臨時駐車場を設置させていただくこととなりました。\n\n配水管の布設作業は、1日あたり約15m～30m程度の掘削を行うため、施工箇所によりましては、一時的にお車の出し入れが難しくなる場合がございます。\n\nその際には大変恐れ入りますが、臨時駐車場へのお車のご移動にご協力をお願いさせていただくことがございます。\n\nなお、臨時駐車場内における盗難や事故等につきましては、誠に申し訳ございませんが、責任を負いかねますので、貴重品の管理や施錠等にご留意いただきますようお願い申し上げます。\n\nできる限りご不便をおかけしないよう努めてまいりますので、安心・安全な工事のため、何卒ご理解とご協力のほどお願い申し上げます。",
    "image_description4": "工事の進捗に伴い、9月25日はゴミの移動を実施いたします。\n\nゴミステーション1のゴミにつきましては、移動先ゴミステーション1へ工事業者が移動させていただきます。\n\n地域の皆様に特別なご対応をお願いするものではございません。今までどおり所定の時間までにゴミをお出しいただければ、ゴミの移動は工事業者が行います。\n\n工事期間中は、地域の皆様にご不便をおかけすることもございますが、引き続き安全かつ円滑に工事を進めてまいりますので、何卒ご理解とご協力を賜りますようお願い申し上げます。",
    "holiday_notice": "本工事では、作業員の安全と健康を守り、適切な休日を確保するため、原則として土曜日・日曜日を休工日としております。特別な事情がない限り、土曜日・日曜日の作業は行わない予定です。\n\n地域の皆様には、工事期間中ご不便をおかけいたしますが、安全に工事を進めてまいりますので、引き続きご理解とご協力をお願いいたします。"
}

SITE_INFO_EN = {
    "construction_name": "Notice Board for Water Distribution Pipe Replacement Work\nas of September 24, 2026",
    "image_file": "撤去・連絡工en.pdf",
    "image_file2": "工事概要en.pdf",
    "image_file3": "臨時駐車場en.pdf",
    "image_file4": "ゴミの移動en.pdf",

    "image_description": """We sincerely appreciate the continued understanding and cooperation of everyone in the community regarding this construction work. We would also like to apologize for the inconvenience caused today to the businesses and households who cooperated with the water outage. Thanks to your cooperation, we were able to remove a valve that was no longer needed. We are truly grateful for your support.\n\nTomorrow, September 25, existing pipe removal and closure work is scheduled to be carried out at the two locations shown in the diagram. Work will begin at the southern location in the morning, and backfilling will be carried out once that work is complete. Work will then move to the northern location.\n\nTraffic restrictions associated with the construction work will be implemented within the restricted area near the railway line. Vehicles will not be able to pass through from either the north or the south, so please use detour routes when traveling near the area.\n\nTraffic control personnel will be stationed around the construction area to ensure everyone’s safety. When passing through the area, please follow the on-site signs and the directions of the traffic control personnel.\n\nGoing forward, the final paving work will be carried out, bringing this construction project to completion.\n\nWe apologize for the continued inconvenience caused by the construction work and traffic restrictions. We will continue to give the highest priority to safety as we carry out the work, and we appreciate your understanding and cooperation until the project is completed.""",

"image_description2": """The construction work will begin with pavement cutting and will be completed with final pavement restoration.\n\nDuring water service connection replacement work, temporary water outages may occur for individual properties. We will notify affected residents in advance when a water outage is necessary, and we appreciate your understanding and cooperation.""",

    "image_description3": """A temporary parking area has been provided with the kind cooperation of a nearby resident.\n\nBecause the water pipe-laying work involves excavating approximately 15 to 30 meters per day, access to your vehicle may become temporarily difficult depending on the construction location.\n\nIn such cases, we may kindly ask residents to move their vehicles to the temporary parking area.\n\nPlease note that we cannot be responsible for theft, accidents, or other incidents within the temporary parking area. We kindly ask you to lock your vehicle and manage your valuables carefully.\n\nWe will do our best to minimize inconvenience, and we appreciate your understanding and cooperation for safe and secure construction work.""",

    "image_description4": """As the construction work progresses, garbage will be relocated on September 25.\n\nGarbage at Garbage Station 1 will be moved to the relocation site, Garbage Station 1, by the construction contractor.\n\nNo special action is required from local residents. Please continue to place your garbage at the usual collection point by the designated time, as before; the construction contractor will take care of moving it.\n\nWe apologize for any inconvenience to the community during the construction period. We will continue to carry out the work safely and smoothly, and we appreciate your understanding and cooperation.""",

    "holiday_notice": """To protect the safety and health of our workers and ensure they have adequate time off, Saturdays and Sundays are generally treated as non-working days for this project. Unless special circumstances arise, no work is planned on those days.\n\nWe apologize for any inconvenience to the community during the construction period. We will continue to carry out the work safely, and we appreciate your continued understanding and cooperation."""
}

def get_board_text():
    return f"""
工事名:
{SITE_INFO["construction_name"]}

次回工事のお知らせ:
{SITE_INFO["image_description"]}

工事の順番:
{SITE_INFO["image_description2"]}

臨時駐車場について:
{SITE_INFO["image_description3"]}

ゴミの移動について:
{SITE_INFO["image_description4"]}

休工日のお知らせ:
{SITE_INFO["holiday_notice"]}
"""


# -------------------------
# ルート
# -------------------------
@app.route("/")
def home():
    return render_template("base.html", site=SITE_INFO, lang="ja")

@app.route("/en")
def home_en():
    return render_template("base.html", site=SITE_INFO_EN, lang="en")

@app.route("/board")
def board():
    edit_id = request.args.get("edit_id", type=int)

    comments = (
        db.session.query(Comment)
        .filter(Comment.parent_id.is_(None))
        .order_by(Comment.id.desc())
        .all()
    )

    replies = (
        db.session.query(Comment)
        .filter(Comment.parent_id.is_not(None))
        .order_by(Comment.id.asc())
        .all()
    )

    edit_comment = None
    if edit_id:
        edit_comment = db.session.get(Comment, edit_id)

    return render_template(
        "take.html",
        comments=comments,
        replies=replies,
        edit_comment=edit_comment,
        site=SITE_INFO,
        lang="ja"
    )

@app.route("/en/board")
def board_en():
    edit_id = request.args.get("edit_id", type=int)

    comments = (
        db.session.query(Comment)
        .filter(Comment.parent_id.is_(None))
        .order_by(Comment.id.desc())
        .all()
    )

    replies = (
        db.session.query(Comment)
        .filter(Comment.parent_id.is_not(None))
        .order_by(Comment.id.asc())
        .all()
    )

    edit_comment = None
    if edit_id:
        edit_comment = db.session.get(Comment, edit_id)

    return render_template(
        "take.html",
        comments=comments,
        replies=replies,
        edit_comment=edit_comment,
        site=SITE_INFO_EN,
        lang="en"
    )

@app.route("/ask_ai", methods=["POST"])
@limiter.limit("5 per minute")
def ask_ai():
    question = request.form.get("question", "").strip()
    lang = request.form.get("lang", "ja").strip() or "ja"

    if not question:
        # このフォームは JavaScript の fetch で送られJSONを期待するため、
        # リダイレクトではなくやさしい文言のJSONを返す。
        message = (
            "Please enter your question."
            if lang == "en"
            else "質問を入力してください。"
        )
        return jsonify({"question": "", "answer": message})

    # 質問が長すぎる場合は、OpenAI APIを呼ばずにその場で返す。
    if len(question) > MAX_QUESTION_LENGTH:
        message = (
            "Sorry, your question is too long. Please keep it within 300 characters."
            if lang == "en"
            else "申し訳ありません。質問文が長すぎます。300文字以内で入力してください。"
        )
        return jsonify({"question": question, "answer": message})

    board_text = get_board_text()

    # PDF全文を毎回渡すのはやめ、質問に関係する箇所だけを Retriever で取得する。
    # 失敗しても空文字が返り、掲示板情報だけで回答を続ける（画面にはエラーを出さない）。
    pdf_context, pdf_chunks_for_log = rag.retrieve_pdf_context(
        app.root_path, question, k=4
    )

    if pdf_context:
        pdf_section = pdf_context
    else:
        pdf_section = "（この質問に関係するPDF資料は見つかりませんでした）"

    # 日本時間（Asia/Tokyo）を明示して「今日」「明日」を求める。
    # Windows / Render では strftime の %-m や %-d、%A（日本語曜日）が
    # 安定しないため、曜日は日本語リストから、日付は f-string で組み立てる。
    weekdays_jp = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

    def format_jp_date(dt):
        return f"{dt.year}年{dt.month}月{dt.day}日（{weekdays_jp[dt.weekday()]}）"

    jst_now = datetime.now(ZoneInfo("Asia/Tokyo"))
    jst_tomorrow = jst_now + timedelta(days=1)

    today = format_jp_date(jst_now)          # 例：2026年7月5日（日曜日）
    tomorrow = format_jp_date(jst_tomorrow)  # 例：2026年7月6日（月曜日）
    current_year = jst_now.year              # 例：2026

    system_message = """
あなたは公共工事の住民向け掲示板の案内AIです。

必ず以下のルールを守ってください。

・掲示板本文とPDF資料に書かれている内容だけをもとに回答してください。
・掲示板本文にもPDF資料にも書かれていない内容は推測しないでください。
・推測で答えないでください。
・工事費、契約内容、責任問題、職人や発注者の評価には答えないでください。
・分からない場合は「公開されている掲示板情報および資料では確認できません。必要に応じて現場担当者へお問い合わせください。」と答えてください。

【日付の判断ルール】
・「今日」「明日」「あさって」などの日付は、user メッセージ内の【現在の日付情報（日本時間）】を必ず基準に判断してください。
・掲示板本文やPDF資料に「7月6日（月曜日）」のように西暦（年）が書かれていない場合は、【現在の日付情報（日本時間）】の「現在の西暦」を補って、その年の日付として判断してください。
・ただし、掲示板本文・PDF資料に書かれていない予定は、日付から推測して答えないでください。書かれていない場合は「確認できません」と答えてください。

【回答言語のルール】
・住民からの質問文の言語を判定し、その言語で回答してください。
・質問が英語なら、必ず英語で回答してください。
・質問が日本語なら、必ず日本語で回答してください。
・掲示板情報が日本語で書かれていても、質問が英語なら英語に訳して回答してください。
・質問文が複数言語の場合は、主に使われている言語で回答してください。

・回答は長くしすぎず、必要な内容を簡潔に伝えてください。
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_message},
                {
                    "role": "user",
                    "content": f"""
【現在の日付情報（日本時間）】
今日：{today}
明日：{tomorrow}
現在の西暦：{current_year}年

以下が掲示板に掲載されている情報です。

【掲示板情報】
{board_text}

【検索されたPDF資料】
（polytech.pdf の中から、この質問に関係する部分だけを検索した結果です）
{pdf_section}

【住民からの質問】
{question}


"""
                }
            ],
            temperature=0.2,
            max_tokens=MAX_OUTPUT_TOKENS,
        )

        ai_answer = response.choices[0].message.content

    except Exception:
        app.logger.exception(
            "OpenAI API呼び出しに失敗しました（question=%r, lang=%s）", question, lang
        )
        ai_answer = (
            "We are sorry. The AI guidance service is currently unavailable. Please try again later."
            if lang == "en"
            else "申し訳ありません。現在AI案内を利用できません。時間をおいて再度お試しください。"
        )

    # 会話履歴を保存する（あとから管理者が確認するため）。
    # 保存に失敗しても、住民への回答表示は止めない。
    try:
        created_at = jst_now.strftime("%Y-%m-%d %H:%M")
        new_log = AiLog(
            question=question,
            answer=ai_answer,
            lang=lang,
            created_at=created_at,
            pdf_chunks=pdf_chunks_for_log or None,
        )
        db.session.add(new_log)
        db.session.commit()

        # 会話履歴用のベクターストアにも保存（回答の根拠には使わない・保管のみ）。
        rag.save_conversation(
            app.root_path, new_log.id, question, ai_answer, lang, created_at
        )
    except Exception:
        app.logger.exception(
            "AiLogの保存またはRAGへの会話履歴保存に失敗しました（question=%r）", question
        )
        db.session.rollback()

    return jsonify({
        "question": question,
        "answer": ai_answer
    })


@app.errorhandler(429)
def ratelimit_handler(e):
    # /ask_ai はJSがJSONレスポンスを期待するfetch実装のため、429もJSONで返す。
    if request.path == "/ask_ai":
        lang = request.form.get("lang", "ja").strip() or "ja"
        message = (
            "Too many questions. Please wait a moment and try again."
            if lang == "en"
            else "質問の回数が多すぎます。しばらく待ってから再度お試しください。"
        )
        return jsonify({"question": "", "answer": message}), 429
    return e


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """管理者ログイン画面。ADMIN_DELETE_PASSWORDと一致したらセッションに記録する。"""
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if ADMIN_DELETE_PASSWORD and hmac.compare_digest(password, ADMIN_DELETE_PASSWORD):
            session["is_admin"] = True
            return redirect(url_for("admin_ai_logs"))
        error = "パスワードが違います。"

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/ai_logs")
def admin_ai_logs():
    """管理者がAI質問履歴を確認するページ。セッションでログイン済みのときだけ表示する。"""
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    logs = db.session.query(AiLog).order_by(AiLog.id.desc()).all()

    return render_template("ai_logs.html", logs=logs)


@app.route("/add_comment", methods=["POST"])
def add_comment():
    name = request.form.get("name", "").strip()
    message = request.form.get("message", "").strip()

    if not name or not message:
        flash("名前とコメントを入力してください。")
        return redirect(url_for("board"))

    new_comment = Comment(
        name=name,
        message=message,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    db.session.add(new_comment)
    db.session.commit()

    flash("コメントを投稿しました。")
    return redirect(url_for("board"))


@app.route("/reply/<int:comment_id>", methods=["POST"])
def reply(comment_id):
    name = request.form.get("reply_name", "").strip()
    message = request.form.get("reply_message", "").strip()

    if not name or not message:
        flash("返信の名前と内容を入力してください。")
        return redirect(url_for("board"))

    parent_comment = db.session.get(Comment, comment_id)
    if not parent_comment:
        flash("返信先のコメントが見つかりません。")
        return redirect(url_for("board"))

    new_reply = Comment(
        parent_id=comment_id,
        name=name,
        message=message,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    db.session.add(new_reply)
    db.session.commit()

    flash("返信を投稿しました。")
    return redirect(url_for("board"))


@app.route("/update/<int:comment_id>", methods=["POST"])
def update(comment_id):
    password = request.form.get("edit_password", "").strip()

    # 訂正は削除と同じ管理者パスワードを要求する（誰でも他人の投稿を書き換えられないようにするため）。
    if not ADMIN_DELETE_PASSWORD or not hmac.compare_digest(password, ADMIN_DELETE_PASSWORD):
        flash("訂正用パスワードが違います。")
        return redirect(url_for("board", edit_id=comment_id))

    comment = db.session.get(Comment, comment_id)
    if not comment:
        flash("編集対象のコメントが見つかりません。")
        return redirect(url_for("board"))

    name = request.form.get("edit_name", "").strip()
    message = request.form.get("edit_message", "").strip()

    if not name or not message:
        flash("編集時は名前と内容を入力してください。")
        return redirect(url_for("board", edit_id=comment_id))

    comment.name = name
    comment.message = message
    db.session.commit()

    flash("コメントを訂正しました。")
    return redirect(url_for("board"))


@app.route("/delete/<int:comment_id>", methods=["POST"])
def delete(comment_id):
    password = request.form.get("delete_password", "").strip()

    if not ADMIN_DELETE_PASSWORD or not hmac.compare_digest(password, ADMIN_DELETE_PASSWORD):
        flash("削除パスワードが違います。")
        return redirect(url_for("board"))

    comment = db.session.get(Comment, comment_id)
    if not comment:
        flash("削除対象が見つかりません。")
        return redirect(url_for("board"))

    # 親コメントなら返信も一緒に削除
    if comment.parent_id is None:
        child_replies = db.session.query(Comment).filter_by(parent_id=comment.id).all()
        for child in child_replies:
            db.session.delete(child)

    db.session.delete(comment)
    db.session.commit()

    flash("コメントを削除しました。")
    return redirect(url_for("board"))


if __name__ == "__main__":
    app.run()