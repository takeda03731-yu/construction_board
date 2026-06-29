import os
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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
    "construction_name": "令和7年度 管路更新（耐震化）事業　土与丸（是石）地区ほか配水管布設替工事掲示板　6月29日現在",
    "image_file": "配水管布設工.pdf",  # staticフォルダ内のファイル名
    "image_file2": "工事概要.pdf",
    "image_file3": "臨時駐車場.pdf",
    "image_file4": "ゴミの移動.pdf",
    "image_description": "日頃より、本工事へのご理解とご協力をいただき、誠にありがとうございます。\n\n工事期間中は、交通規制や迂回などにより、地域の皆様にはご不便をおかけしておりますが、皆様の温かいご協力のおかげで、安全に工事を進めることができております。改めまして、心より感謝申し上げます。\n\nこのたび、工事再開の日程が決まりましたので、お知らせいたします。工事は7月6日（月曜日）より再開し、6月16日に施工した箇所の続きから作業を進める予定です。\n\n工事再開に伴い、交通規制区間は前回よりさらに延長する予定です。そのため、南側から北側への通り抜けは、引き続きご利用いただけません。また、図に示しております三叉路付近での施工を予定しておりますので、南側の踏切付近からの通り抜けにつきましても、ご利用いただけなくなる見込みです。\n\nお車で通行される際は、お手数をおかけいたしますが、線路手前より迂回していただきますようお願いいたします。\n\n現地では、安全確保のため交通誘導員を配置する予定です。通行の際は、交通誘導員の案内に従っていただき、図面に記載しております迂回路をご利用くださいますようお願いいたします。なお、北側からの車両の進入につきましても、引き続き制限を行います。中型車両をご利用の方は、お手数をおかけいたしますが、図面に記載しております指定経路からご通行くださいますよう、ご協力をお願いいたします。\n\n迂回路には道路幅が狭い箇所や見通しの悪い箇所がありますので、通行の際は十分ご注意ください。\n\n長期間にわたりご不便をおかけしておりますが、皆様のご理解とご協力に深く感謝申し上げます。今後も安全を最優先に、できる限り皆様の生活への影響を少なくできるよう努めながら工事を進めてまいります。工事再開後も、ご不便をおかけいたしますが、引き続きご理解とご協力を賜りますよう、よろしくお願い申し上げます。",
    "image_description2": "工事は舗装版切断工から始まり、本舗装復旧工で終了となります。給水分岐替工では、個別に断水が発生します。断水の際は事前にお知らせしますので、ご理解とご協力をお願い致します。",
    "image_description3": "このたび、近隣の住民様のご厚意により、臨時駐車場を設置させていただくこととなりました。\n\n配水管の布設作業は、1日あたり約15m～30m程度の掘削を行うため、施工箇所によりましては、一時的にお車の出し入れが難しくなる場合がございます。\n\nその際には大変恐れ入りますが、臨時駐車場へのお車のご移動にご協力をお願いさせていただくことがございます。\n\nなお、臨時駐車場内における盗難や事故等につきましては、誠に申し訳ございませんが、責任を負いかねますので、貴重品の管理や施錠等にご留意いただきますようお願い申し上げます。\n\nできる限りご不便をおかけしないよう努めてまいりますので、安心・安全な工事のため、何卒ご理解とご協力のほどお願い申し上げます。",
    "image_description4": "このたび、工事の再開日が7月6日（月曜日）に決まりましたので、ゴミの移動対応を再開させていただきます。\n\nなお、皆様に新たなご対応をお願いするものではございません。これまでと同様に、ゴミは所定のゴミステーションへお出しください。回収日当日の午前8時頃に、工事関係者が移動先のゴミステーションへ運搬いたします。\n\n今回は、工事に伴う交通規制範囲の拡大により、前回とは異なるゴミステーションにつきましても移動対応を実施いたします。図面に記載しております「メゾン・ド・モンマルトル」前のゴミステーションを含め、追加となるゴミステーションについても対応いたします。\n\nこれまでと同様、皆様には通常どおりゴミをお出しいただくだけで結構です。移動作業は当社にて対応いたしますので、引き続きご理解とご協力のほど、よろしくお願い申し上げます。",
    "holiday_notice": "次回の工事再開は、7月6日（月曜日）を予定しております。そのため、7月5日（日曜日）まで休工とさせていただきます。\n\n本工事では、作業員の安全確保や健康管理、ならびに建設業界における働き方改革の取り組みの一環として、原則として土曜日・日曜日を休工日としております。\n\n近年、建設業界では、安全で質の高い施工を継続するため、適切に休日を確保しながら工事を進める取り組みが進められています。\n\nそのため、本工事におきましても、特別な事情がない限り、土曜日・日曜日の作業は行わない予定です。\n\n地域の皆様には、ご不便をおかけすることもございますが、安全で円滑な工事の実施のため、何卒ご理解とご協力を賜りますよう、よろしくお願い申し上げます。"
}

SITE_INFO_EN = {
    "construction_name": "Notice Board for Water Distribution Pipe Replacement Work as of June 29, 2026",
    "image_file": "配水管布設工en.pdf",
    "image_file2": "工事概要en.pdf",
    "image_file3": "臨時駐車場en.pdf",
    "image_file4": "ゴミの移動en.pdf",

    "image_description": """Thank you very much for your continued understanding and cooperation regarding this construction project.\n\nDuring the construction period, we apologize for any inconvenience caused by traffic restrictions and detours. Thanks to your kind cooperation, we have been able to carry out the work safely. We sincerely appreciate your continued support.\n\nWe would like to inform you that the construction restart date has now been confirmed. Construction will resume on Monday, July 6, continuing from the section where work stopped on June 16.\n\nAs construction resumes, the traffic restriction area will be extended beyond the previous work zone. Therefore, through traffic from the south side to the north side will continue to be unavailable. In addition, as work is scheduled near the three-way intersection shown on the map, through traffic near the railroad crossing on the south side will also be unavailable.\n\nIf you are traveling by car, we kindly ask that you use the designated detour before reaching the railroad crossing.\n\nFor your safety, traffic controllers will be stationed at the construction site. Please follow their instructions and use the detour routes shown on the map. Vehicle access from the north side will also continue to be restricted. Drivers of medium-sized vehicles are kindly requested to use the designated route shown on the map.\n\nPlease note that some sections of the detour route are narrow and have limited visibility. We kindly ask you to drive with extra caution.\n\nWe sincerely apologize for the inconvenience caused over this extended construction period and greatly appreciate your understanding and cooperation.\n\nWe will continue to place the highest priority on safety while making every effort to minimize the impact on the daily lives of local residents.\n\nWe appreciate your continued understanding and cooperation as construction resumes. Thank you for your patience and support.""",

    "image_description2": """The construction work will begin with pavement cutting and will be completed with final pavement restoration.

During water service connection replacement work, temporary water outages may occur for individual properties.

When a water outage is necessary, we will notify affected residents in advance. Thank you for your understanding and cooperation.""",

    "image_description3": """A temporary parking area has been provided with the kind cooperation of a nearby resident.

Depending on the construction location, access to some private parking spaces may become temporarily difficult.

In such cases, we may kindly ask residents to move their vehicles to the temporary parking area.

Please note that we cannot be responsible for theft, accidents, or damage within the temporary parking area. We kindly ask you to lock your vehicle and manage your valuables carefully.

We will do our best to minimize inconvenience and appreciate your cooperation for safe construction work.""",

    "image_description4": """We would like to inform you that construction will resume on Monday, July 6. Accordingly, we will also resume our temporary waste collection relocation service.\n\nPlease note that no additional action is required from residents. As before, simply place your garbage at your usual designated waste collection station. Our staff will move it to the temporary collection location at approximately 8:00 a.m. on the collection day.\n\nDue to the expansion of the construction area, we will also relocate waste from additional collection stations that were not included previously. This includes the waste collection station in front of Maison de Montmartre, as shown on the map, as well as the newly designated collection stations.\n\nAs always, you only need to place your garbage at your usual collection station. Our staff will take care of moving it to the temporary collection location. We sincerely appreciate your continued understanding and cooperation.""",

    "holiday_notice": """The next phase of construction is scheduled to resume on Monday, July 6. Therefore, construction work will be suspended until Sunday, July 5.\n\nAs part of our commitment to worker safety, health management, and improved working conditions in the construction industry, construction work is generally suspended on Saturdays and Sundays.\n\nIn recent years, the construction industry has been promoting appropriate work schedules with regular days off to ensure safe, high-quality, and sustainable construction.\n\nAccordingly, unless special circumstances arise, no construction work is planned on Saturdays or Sundays for this project.\n\nWe apologize for any inconvenience this may cause and sincerely appreciate your understanding and cooperation. We will continue to prioritize safety and strive to carry out the construction work as safely and smoothly as possible."""
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
        lang="en"
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

    return jsonify({
    "question": question,
    "answer": ai_answer
})


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