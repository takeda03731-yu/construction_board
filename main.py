import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
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
    "construction_name": "令和7年度 管路更新（耐震化）事業　土与丸（是石）地区ほか配水管布設替工事掲示板　8月20日現在",
    "image_file": "給水分岐替工.pdf",  # staticフォルダ内のファイル名
    "image_file2": "工事概要.pdf",
    "image_file3": "臨時駐車場.pdf",
    "image_file4": "ゴミの移動.pdf",
    "image_description": "日頃より、本工事の実施に際し、地域の皆様には多大なるご理解とご協力を賜り、心より御礼申し上げます。\n\n明日8月21日（金曜日）は、図に示した給水分岐替工事箇所の「4番」「5番」および「6番」を施工する予定です。\n\n工事に伴い、対象となるご家庭におきましては、一時的に断水させていただく必要がございます。特に「5番」の給水管につきましては、図に示すとおり、接続先に複数の宅地があるため、給水管の接続作業を行う際に、対象となる範囲で断水を実施いたします。\n\n断水を伴う接続作業につきましては、水道企業団の担当者の方に現地へお越しいただき、施工方法や安全性を十分に確認していただいたうえで、その立会いのもと慎重に実施いたします。対象となる皆様にはご不便をおかけして誠に申し訳ございませんが、安全かつ確実な施工のため、何卒ご理解とご協力をお願いいたします。\n\nまた、工事に伴う交通規制につきましては、従来の規制範囲に戻ります。北側からは通り抜けができませんので、お車で通行される際は、迂回路をご利用くださいますようお願いいたします。\n\nなお、中型車両につきましても、通行可能な経路が限られております。ご不便をおかけして誠に申し訳ございませんが、目的地に応じた適切な経路をご利用くださいますようお願いいたします。\n\n地域の皆様には、引き続きご不便とご迷惑をおかけいたしますが、水道企業団のご指導のもと緊密に連携し、安全を最優先に工事を進めてまいります。工事の安全かつ円滑な実施に向け、何卒ご理解とご協力を賜りますよう、よろしくお願い申し上げます。",
    "image_description2": "工事は舗装版切断工から始まり、本舗装復旧工で終了となります。給水分岐替工では、個別に断水が発生します。断水の際は事前にお知らせしますので、ご理解とご協力をお願い致します。",
    "image_description3": "このたび、近隣の住民様のご厚意により、臨時駐車場を設置させていただくこととなりました。\n\n配水管の布設作業は、1日あたり約15m～30m程度の掘削を行うため、施工箇所によりましては、一時的にお車の出し入れが難しくなる場合がございます。\n\nその際には大変恐れ入りますが、臨時駐車場へのお車のご移動にご協力をお願いさせていただくことがございます。\n\nなお、臨時駐車場内における盗難や事故等につきましては、誠に申し訳ございませんが、責任を負いかねますので、貴重品の管理や施錠等にご留意いただきますようお願い申し上げます。\n\nできる限りご不便をおかけしないよう努めてまいりますので、安心・安全な工事のため、何卒ご理解とご協力のほどお願い申し上げます。",
    "image_description4": "工事の進捗に伴い、8月19日（水曜日）より、ゴミの移動を再開いたします。\n\n「ゴミステーション1」に出されたゴミは、工事業者が「移動先ゴミステーション1」まで移動いたします。\n\n地域の皆様に特別なご対応をお願いするものではございません。これまでどおり、所定の時間までに「ゴミステーション1」へゴミをお出しください。ゴミの移動は工事業者が行います。\n\n地域の皆様にはご不便をおかけいたしますが、何卒ご理解とご協力を賜りますよう、よろしくお願い申し上げます。",
    "holiday_notice": "本工事では、作業員の安全確保や健康管理、ならびに建設業界における働き方改革の取り組みの一環として、原則として土曜日・日曜日を休工日としております。\n\n近年、建設業界では、安全で質の高い施工を継続するため、適切に休日を確保しながら工事を進める取り組みが進められています。\n\nそのため、本工事におきましても、特別な事情がない限り、土曜日・日曜日の作業は行わない予定です。\n\n地域の皆様には、ご不便をおかけすることもございますが、安全で円滑な工事の実施のため、何卒ご理解とご協力を賜りますよう、よろしくお願い申し上げます。"
}

SITE_INFO_EN = {
    "construction_name": "Notice Board for Water Distribution Pipe Replacement Work as of August 20, 2026",
    "image_file": "給水分岐替工en.pdf",
    "image_file2": "工事概要en.pdf",
    "image_file3": "臨時駐車場en.pdf",
    "image_file4": "ゴミの移動en.pdf",

    "image_description": """We would like to express our sincere gratitude to all local residents for your continued understanding and cooperation regarding this construction work.\n\nTomorrow, Friday, August 21, water service connection replacement work is scheduled to be carried out at locations No. 4, No. 5, and No. 6, as shown in the diagram.\n\nAs part of the work, water service will need to be temporarily suspended for the affected households. In particular, the water service pipe at location No. 5 supplies multiple properties, as shown in the diagram. Therefore, water service will be temporarily suspended within the affected area while the pipe connection work is carried out.\n\nFor the connection work requiring a temporary water service suspension, a representative of the water authority will attend the site and carefully review the construction method and safety arrangements. The work will then be carried out with the utmost care under the representative’s supervision. We sincerely apologize for the inconvenience caused to those affected and kindly ask for your understanding and cooperation to ensure the safe and reliable completion of the work.\n\nRegarding traffic restrictions, the closure area will return to its previous arrangement. Through traffic from the north will not be possible, so drivers are kindly requested to use the designated detour route.\n\nPlease note that the available routes for medium-sized vehicles will also be limited. We sincerely apologize for the inconvenience and kindly ask drivers to use the appropriate route according to their destination.\n\nWe apologize for the continued inconvenience caused to local residents. Under the guidance of the water authority, we will continue to work in close cooperation with all parties involved and proceed with the construction while giving the highest priority to safety. We sincerely appreciate your understanding and cooperation in ensuring the safe and smooth completion of the work.""",

"image_description2": """The construction work will begin with pavement cutting and will be completed with final pavement restoration.

During water service connection replacement work, temporary water outages may occur for individual properties.

When a water outage is necessary, we will notify affected residents in advance. Thank you for your understanding and cooperation.""",

    "image_description3": """A temporary parking area has been provided with the kind cooperation of a nearby resident.

Depending on the construction location, access to some private parking spaces may become temporarily difficult.

In such cases, we may kindly ask residents to move their vehicles to the temporary parking area.

Please note that we cannot be responsible for theft, accidents, or damage within the temporary parking area. We kindly ask you to lock your vehicle and manage your valuables carefully.

We will do our best to minimize inconvenience and appreciate your cooperation for safe construction work.""",

    "image_description4": """Due to the progress of the construction work, the relocation of garbage will resume on Wednesday, August 19.\n\nGarbage placed at “Garbage Collection Point 1” will be moved by the construction contractor to “Temporary Garbage Collection Point 1.”\n\nNo special action is required from local residents. Please continue to place your garbage at “Garbage Collection Point 1” by the designated collection time as usual. The construction contractor will handle the relocation of the garbage.\n\nWe apologize for any inconvenience this may cause and sincerely appreciate your understanding and cooperation.""",

    "holiday_notice": """As part of our efforts to ensure the safety and well-being of our workers and to promote work-style reform in the construction industry, work on this project will generally be suspended on Saturdays and Sundays.\n\nIn recent years, the construction industry has been working to secure appropriate rest days in order to maintain safe, high-quality construction practices.\n\nAccordingly, no construction work is scheduled on Saturdays or Sundays for this project unless there are exceptional circumstances.\n\nWe apologize for any inconvenience this may cause local residents. We sincerely appreciate your understanding and cooperation as we work to carry out the project safely and smoothly."""
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
        db.session.rollback()

    return jsonify({
        "question": question,
        "answer": ai_answer
    })


@app.route("/admin/ai_logs")
def admin_ai_logs():
    """
    管理者がAI質問履歴を確認するページ。
    ?password=... が ADMIN_DELETE_PASSWORD と一致したときだけ表示する。
    """
    password = request.args.get("password", "")

    # パスワード未設定、または不一致の場合は表示しない（404で存在を隠す）。
    if not ADMIN_DELETE_PASSWORD or password != ADMIN_DELETE_PASSWORD:
        abort(404)

    logs = db.session.query(AiLog).order_by(AiLog.id.desc()).all()

    return render_template("ai_logs.html", logs=logs, password=password)


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

    if password != ADMIN_DELETE_PASSWORD:
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