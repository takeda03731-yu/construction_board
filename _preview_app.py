from flask import Flask, render_template

app = Flask(__name__)

SITE_INFO = {
    "construction_name": "令和7年度 管路更新（耐震化）事業　土与丸（是石）地区ほか配水管布設替工事掲示板　7月30日現在",
    "image_file": "給水分岐替工.pdf",
    "image_file2": "工事概要.pdf",
    "image_file3": "臨時駐車場.pdf",
    "image_file4": "ゴミの移動.pdf",
    "image_description": "日頃より、本工事へのご理解とご協力を賜り、誠にありがとうございます。\n\n皆様のご協力のおかげをもちまして、給水分岐替工に先立って実施しておりました舗装版切断工は、本日7月30日（木曜日）にすべて完了いたしました。なお、明日7月31日（金曜日）は休工とさせていただきます。\n\n今後は、8月3日（月曜日）から図に示した箇所の防護コンクリート養生の撤去および埋戻しを行い、8月4日（火曜日）から給水分岐替工を本格的に開始する予定です。\n\n給水分岐替工に伴い、各ご家庭・事業所において個別に断水が発生いたします。断水の日時につきましては、対象となる皆様へ事前にお知らせいたしますので、ご理解とご協力をお願いいたします。\n\nまた、8月3日以降の工事では、作業の進捗や時間帯により、北側・南側の両方向からの通行が難しくなる場合がございます。お車で通行される際は、迂回路のご利用をご検討くださいますようお願いいたします。\n\n地域の皆様には、引き続きご不便をおかけいたしますが、安全に十分配慮しながら工事を進めてまいりますので、何卒ご理解とご協力を賜りますよう、よろしくお願い申し上げます。",
    "image_description2": "工事は舗装版切断工から始まり、本舗装復旧工で終了となります。給水分岐替工では、個別に断水が発生します。断水の際は事前にお知らせしますので、ご理解とご協力をお願い致します。",
    "image_description3": "このたび、近隣の住民様のご厚意により、臨時駐車場を設置させていただくこととなりました。\n\n配水管の布設作業は、1日あたり約15m～30m程度の掘削を行うため、施工箇所によりましては、一時的にお車の出し入れが難しくなる場合がございます。\n\nその際には大変恐れ入りますが、臨時駐車場へのお車のご移動にご協力をお願いさせていただくことがございます。\n\nなお、臨時駐車場内における盗難や事故等につきましては、誠に申し訳ございませんが、責任を負いかねますので、貴重品の管理や施錠等にご留意いただきますようお願い申し上げます。\n\nできる限りご不便をおかけしないよう努めてまいりますので、安心・安全な工事のため、何卒ご理解とご協力のほどお願い申し上げます。",
    "image_description4": "検査期間となりましたので、当面の間、工事に伴うゴミの移動は実施いたしません。\n\nゴミは、これまでどおり所定のゴミステーションへお出しくださいますようお願いいたします。\n\nなお、工事の進捗により再度ゴミの移動が必要となる際は、事前に掲示板にてお知らせいたします。\n\nその際は、ご不便をおかけいたしますが、ご理解とご協力のほど、よろしくお願い申し上げます。",
    "holiday_notice": "8月2日（土曜日）・8月3日（日曜日）は、休工とさせていただきます。\n\nご不便をおかけいたしますが、何卒ご理解とご協力を賜りますようお願い申し上げます。",
}


class FakeComment:
    def __init__(self, id, name, message, created_at):
        self.id = id
        self.name = name
        self.message = message
        self.created_at = created_at
        self.parent_id = None


@app.route("/")
def home():
    return render_template("base.html", site=SITE_INFO, lang="ja")


@app.route("/en")
def home_en():
    return render_template("base.html", site=SITE_INFO, lang="en")


@app.route("/board")
def board():
    comments = [FakeComment(1, "近隣住民", "テストコメントです。よろしくお願いします。", "2026-08-01 10:00")]
    return render_template("take.html", lang="ja", comments=comments, replies=[], edit_comment=None)


@app.route("/en/board")
def board_en():
    comments = [FakeComment(1, "Local Resident", "This is a test comment.", "2026-08-01 10:00")]
    return render_template("take.html", lang="en", comments=comments, replies=[], edit_comment=None)


@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    return {"question": "", "answer": ""}


@app.route("/add_comment", methods=["POST"])
def add_comment():
    return "ok"


@app.route("/reply/<int:comment_id>", methods=["POST"])
def reply(comment_id):
    return "ok"


@app.route("/update/<int:comment_id>", methods=["POST"])
def update(comment_id):
    return "ok"


@app.route("/delete/<int:comment_id>", methods=["POST"])
def delete(comment_id):
    return "ok"


if __name__ == "__main__":
    app.run(port=5051)
