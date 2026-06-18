import os
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, ForeignKey
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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


with app.app_context():
    db.create_all()


# -------------------------
# 表示用固定データ
# -------------------------
SITE_INFO = {
    "construction_name": "令和7年度 管路更新（耐震化）事業　土与丸（是石）地区ほか配水管布設替工事掲示板　6月16日現在",
    "image_file": "配水管布設工.pdf",  # staticフォルダ内のファイル名
    "image_file2": "工事概要.pdf",
    "image_file3": "臨時駐車場.pdf",
    "image_file4": "ゴミの移動.pdf",
    "image_description": "日頃より、本工事へのご理解とご協力をいただき、誠にありがとうございます。\n\n工事期間中は、交通規制や迂回のお願いなどにより、地域の皆様にはご不便をおかけしておりますが、皆様の温かいご協力に支えられながら、日々安全に作業を進めることができております。改めまして、心より御礼申し上げます。\n\nこのたび、工事を進めるにあたり、所定の手続きや確認を要する事項が生じたため、しばらくの間、休工とさせていただくこととなりました。\n\n順調に作業を進めることができておりましたところ、地域の皆様にはご心配とご迷惑をおかけすることとなり、誠に申し訳ございません。\n\n次回の工事再開は、7月上旬頃を予定しております。再開日程が確定次第、できるだけ早めにお知らせいたします。\n\n工事再開後は、6月16日に施工した箇所の続きから作業を再開する予定です。\n\n交通規制区間につきましては、前回の規制範囲からさらに延長する予定としております。そのため、南側から北側への通り抜けは引き続きご利用いただけない見込みです。\n\nまた、図に示しております三叉路付近での施工を予定しているため、南側の踏切付近からの通り抜けにつきましても、できなくなる見込みです。\n\nお車で通行される際は、お手数をおかけいたしますが、線路手前より迂回していただきますようお願いいたします。\n\n現地では、安全確保のため、交通誘導員の方を配置する予定です。通行の際は、交通誘導員の方の案内をご確認いただき、図面に記載しております迂回路をご利用くださいますようお願いいたします。\n\nなお、北側からの車両の進入につきましても、引き続き制限を行う予定です。中型車両をご利用の方は、恐れ入りますが、図面に記載しております指定経路からの進入にご協力をお願いいたします。\n\n迂回路には、道路幅の狭い箇所や見通しの悪い箇所もございますので、通行の際は十分ご注意くださいますようお願いいたします。\n\n長期間にわたりご不便をおかけしておりますが、皆様のご理解とご協力に深く感謝申し上げます。\n\n今後も安全を最優先に、できる限り皆様の生活への影響を抑えながら工事を進めてまいります。\n\n工事再開の際は、引き続きご理解とご協力を賜りますよう、よろしくお願い申し上げます。",
    "image_description2": "工事は舗装版切断工から始まり、本舗装復旧工で終了となります。給水分岐替工では、個別に断水が発生します。断水の際は事前にお知らせしますので、ご理解とご協力をお願い致します。",
    "image_description3": "このたび、近隣の住民様のご厚意により、臨時駐車場を設置させていただくこととなりました。\n\n配水管の布設作業は、1日あたり約15m～30m程度の掘削を行うため、施工箇所によりましては、一時的にお車の出し入れが難しくなる場合がございます。\n\nその際には大変恐れ入りますが、臨時駐車場へのお車のご移動にご協力をお願いさせていただくことがございます。\n\nなお、臨時駐車場内における盗難や事故等につきましては、誠に申し訳ございませんが、責任を負いかねますので、貴重品の管理や施錠等にご留意いただきますようお願い申し上げます。\n\nできる限りご不便をおかけしないよう努めてまいりますので、安心・安全な工事のため、何卒ご理解とご協力のほどお願い申し上げます。",
    "image_description4": "6月2日より、工事の進捗に伴い、ゴミの収集運搬車が工事区間内へ進入できなくなるため、ゴミの収集を継続できるよう、一時的にゴミを収集運搬車が通行可能な場所へ移動する対応を開始いたします。\n\nゴミの移動作業は、収集日の午前8時頃から開始する予定としております。\n\n住民の皆様に新たな作業をお願いするものではございませんので、これまでと同様に、収集日の朝、所定の時間までにゴミステーションへお出しいただければ、弊社にて移動対応を行います。\n\nなお、ゴミの移動が完了しましたら、ゴミステーションに「本日のゴミの移動は完了しました」と記載した案内を掲示いたします。\n\nその後に持ち込まれたゴミにつきましては、収集に間に合わない場合がございます。その際は、恐れ入りますが次回の収集日にお出しいただくか、案内に記載しております移動先（ブルーシート設置箇所）までお持ちいただきますようお願いいたします。\n\n工事期間中は、できる限り皆様にご不便やご負担をおかけしないよう努めてまいります。\n\n安全かつ円滑な工事のため、何卒ご理解とご協力を賜りますようお願い申し上げます。",
    "holiday_notice": "このたび、工事を進めるにあたり、所定の手続きや確認を要する事項が生じたため、しばらくの間、休工とさせていただくこととなりました。次回工事再開は、7月上旬頃を予定しております。\n\n本工事では、作業員の安全確保や健康管理、ならびに建設業界における働き方改善の取り組みの一環として、原則として土曜日・日曜日を休工日としております。\n\n近年、建設業界では、安全で持続的な施工体制を維持するため、適切に休日を確保しながら工事を進める取り組みが進められております。\n\nそのため、本工事につきましても、特別な事情がない限り、土曜日・日曜日の作業は行わない予定としております。\n\n地域の皆様にはご不便をおかけする場面もございますが、安全かつ円滑に工事を進めていくため、何卒ご理解とご協力を賜りますようお願い申し上げます。"
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
    return render_template("base.html", site=SITE_INFO)


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
        edit_comment=edit_comment
    )

@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    question = request.form.get("question", "").strip()

    if not question:
        flash("質問を入力してください。")
        return redirect(url_for("board"))

    board_text = get_board_text()

    system_message = """
あなたは公共工事の住民向け掲示板の案内AIです。

必ず以下のルールを守ってください。

・掲示板本文に書かれている内容だけをもとに回答してください。
・推測で答えないでください。
・工事費、契約内容、責任問題、職人や発注者の評価には答えないでください。
・分からない場合は「公開されている掲示板情報では確認できません。必要に応じて現場担当者へお問い合わせください。」と答えてください。
・住民の方に対して、丁寧で分かりやすい日本語で回答してください。
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
以下が掲示板に掲載されている情報です。

【掲示板情報】
{board_text}

【住民からの質問】
{question}
"""
                }
            ],
            temperature=0.2,
        )

        ai_answer = response.choices[0].message.content

    except Exception:
        ai_answer = "申し訳ありません。現在AI案内を利用できません。時間をおいて再度お試しください。"

    return render_template(
        "take.html",
        comments=db.session.query(Comment).filter(Comment.parent_id.is_(None)).order_by(Comment.id.desc()).all(),
        replies=db.session.query(Comment).filter(Comment.parent_id.is_not(None)).order_by(Comment.id.asc()).all(),
        edit_comment=None,
        ai_question=question,
        ai_answer=ai_answer
    )


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