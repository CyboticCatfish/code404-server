__author__ = 'leviwright'

from flask import Flask, request, make_response, render_template
from errors import *
from database import engine, User, Level, Token, Subscription
from sqlalchemy import sql, asc
from converters import user_to_xml
from hashlib import sha256
from datetime import datetime, timedelta
from os import urandom
from binascii import b2a_hex, a2b_hex
import re
import random


app = Flask(__name__)
app.debug = True


def get_arg(name):
    try:
        return request.args.get(name)
    except IndexError:
        return None


def get_header(name):
    try:
        return request.headers[name]
    except KeyError:
        return None


def get_user():
    try:
        user_id = int(get_arg("user_id"))
    except:
        raise InvalidUser()

    user_name = get_arg("user_name")

    print(user_name, user_id)

    if user_id is None and user_name is None:
        raise NoUser()
    elif user_id is not None:
        x = sql.select([User]).where(User.id == user_id).limit(1)
        conn = engine.connect()
        for row in conn.execute(x):
            return row
    elif user_name is not None:
        return "test"


def escape_xml(text):
    return text.replace("<", "&lt;").replace(">", "&gt;")


def make_status(status, message, data=None):
    response = "<?xml version='1.0'?>"
    response += "<response status='%s'>" % status
    response += "<message>"
    response += escape_xml(message)
    response += "</message>"
    if data:
        response += "<data>" + str(data) + "</data>"
    response += "</response>"
    return response


def make_error(message):
    # return make_response(make_status("failed", message), 500)
    print(message)
    return "undefined"


def get_user_from_id(user_id):
    conn = engine.connect()
    query = sql.select(User).where(User.id == user_id).limit(1)
    for row in conn.execute(query):
        return row
    else:
        return None


def get_user_id_from_token(token=None):
    print("test", token)
    if token is None:
        token = get_header("token")
        if token is None:
            raise MissingInformation("token")

    token_bin = a2b_hex(token)
    print(token_bin)
    conn = engine.connect()
    query = sql.select([Token.__table__])\
        .limit(1)\
        .order_by(asc(Token.expire))\
        .where(Token.token == token_bin)

    rows = conn.execute(query).fetchall()
    print(rows)

    for row in rows:
        print(row)
        try:
            if row[Token.expire] < datetime.now():
                raise InvalidInformation("token", "Token has expired")
            else:
                return row["user_id"]
        except:
            return row["user_id"]
    else:
        raise InvalidInformation("token", "Not a valid token.")


def login(username, password):

    hasher = sha256()
    hasher.update(password.encode("utf8"))
    pass_hash = hasher.digest()

    print(username, pass_hash)
    conn = engine.connect()
    query = sql.select([User.__table__]).where(
        (User.login == username.lower())
        & (User.public == 1)
    )

    print(query)

    for row in conn.execute(query).fetchall():
        print(row.passhash)
        return row
    else:
        return None


@app.route("/", methods=["GET"])
def hello_world():
    return "Hello, world!"


@app.route("/level", methods=["GET"])
def web_level():
    try:
        level_id = get_arg("id")
        if level_id is None:
            raise MissingInformation("id")
        conn = engine.connect()
        query = sql.select([Level]).where(Level.id == level_id)
        rows = conn.execute(query)

        for row in rows.fetchall():
            # print(row)
            return render_template("level.html", level=row)
        else:
            raise InvalidInformation("id", "Not found")
    except MissingInformation as e:
        return make_error(e.message)
    except InvalidInformation as e:
        return make_error(e.message)


@app.route("/level/get", methods=["GET"])
def get_level():
    # get arguments
    try:
        level_id = get_arg("id")

        if level_id is None:
            raise MissingInformation("id")
    except MissingInformation as e:
        return make_error(e.message)

    # check arguments
    try:
        try:
            level_id = int(level_id)
        except ValueError:
            raise InvalidInformation("id", "Not a number.")
    except InvalidInformation as e:
        return make_error(e.message)

    # perform query
    try:
        conn = engine.connect()
        query = sql.select([Level.creator, Level.timestamp, Level.name]).where(Level.id == level_id).limit(1)
        rows = conn.execute(query)
        for row in rows.fetchall():
            print(row[2])
            return open("levels/%s/%s-%s.lvl" % (row[0], row[2], row[1])).read()
        else:
            raise InvalidInformation("id", "No level exists with this ID")
    except InvalidInformation as e:
        return make_error(e.message)


@app.route("/level/subscribe", methods=["POST"])
def subscribe_to_level():
    try:
        token = get_header("token")
        level_id = get_arg("level_id")

        if token is None:
            raise MissingInformation("token")
        if level_id is None:
            raise MissingInformation("level_id")
    except MissingInformation as e:
        return make_error(e.message)

    try:
        user_id = get_user_id_from_token(token)
    except InvalidInformation as e:
        return make_error(e.message)

    print(level_id, user_id)

    conn = engine.connect()
    query = sql.insert(
        Subscription,
        values={Subscription.level_id: level_id,
                Subscription.user_id: user_id}
    )
    x = conn.execute(query)
    # if x:
    #     print("1")
    # else:
    #     print("2")

    return make_status("success", "Subscribed to level")


@app.route("/levels/post", methods=["POST"])
def upload_level():
    try:
        user_id = get_user_id_from_token()
    except MissingInformation as e:
        return make_error(e.message)
    except InvalidInformation as e:
        return make_error(e.message)

    try:
        name = get_header("level-name")
        public = get_header("public")
        if name is None:
            raise MissingInformation("level-name")
        if public is None:
            public = True
        else:
            try:
                public = bool(int(public))
            except ValueError:
                raise InvalidInformation("public", "Not a number.")
    except MissingInformation as e:
        return make_error(e.message)
    except InvalidInformation as e:
        return make_error(e.message)

    timestamp = datetime.now()

    conn = engine.connect()
    query = sql.insert(
        (Level.creator, Level.name, Level.timestamp, Level.public),
        values=(user_id, name, timestamp, public)
    )

    f = request.files["level"]
    f.save("levels/%s/%s-%s.lvl" % (user_id, name, timestamp))
    return make_status("success", "Level saved.")


@app.route("/level/get/list", methods=["GET"])
def get_level_list():
    try:
        user = get_user()
    except NoUser as e:
        return make_error(e.message)
    except InvalidUser as e:
        return make_error(e.message)

    return make_status("success", "Got user", user_to_xml(user))


@app.route("/user/create", methods=["POST"])
def create_user():
    conn = engine.connect()
    try:
        login = get_header("login")
        name = get_header("name")
        password = get_header("password")
        public = get_header("public")

        if login is None:
            raise MissingInformation("login")
        if name is None:
            raise MissingInformation("name")
        if password is None:
            raise MissingInformation("password")

    except MissingInformation as e:
        return make_error(e.message)

    try:
        # check login is valid
        login = login.lower()

        # max 32 chars
        if len(login) > 32:
            raise InvalidInformation("login", "Must be less that 32 characters.")

        # alphanumerics only
        if re.match("[^a-z0-9]", login):
            raise InvalidInformation("login", "Can only contain alphanumeric characters")

        # check unique
        if bool(len(tuple(*conn.execute(sql.select([User.id]).where(User.login == login))))):
            raise InvalidInformation("login", "Login is in use")

        # check screen name is valid
        if len(name) > 32:
            raise InvalidInformation("name", "Must be less that 32 characters")

        # check password is valid
            # IT IS ALWAYS VALID

        # check public is valid
        if public is None:
            public = "1"
        else:
            try:
                public = bool(int(public))
            except ValueError:
                raise InvalidInformation("public", "Must be integer")

    except InvalidInformation as e:
        return make_error(e.message)

    # all information is valid
    # hash password
    hasher = sha256()
    hasher.update(password.encode("utf8"))

    pass_hash = hasher.digest()

    # push to DB
    query = sql.insert(
        [User.login, User.username, User.passhash, User.public],
        values=(login, name, pass_hash, public)
    )
    res = conn.execute(query)
    return make_status("success", "User created")


@app.route("/user/login", methods=["POST"])
def get_token():
    print(request.data)
    try:
        username = get_header("username")
        password = get_header("password")
        if username is None:
            raise MissingInformation("username")
        if password is None:
            raise MissingInformation("password")
    except MissingInformation as e:
        return make_error(e.message)

    try:
        user = login(username, password)
        if user is None:
            raise InvalidLogin
    except InvalidLogin as e:
        return make_error(e.message)

    hasher = sha256()
    hasher.update(urandom(16))
    token = hasher.digest()

    expire = datetime.now() + timedelta(weeks=52)

    conn = engine.connect()
    query = sql.insert(Token.__table__, values={
        Token.token: token,
        Token.user_id: user.id,
        Token.expire: expire
    })

    res = conn.execute(query)

    token_hex = b2a_hex(token)

    return token_hex


@app.route("/user/subscriptions", methods=["GET"])
def get_subscriptions():
    try:
        token = get_header("token")
        if token is None:
            user_id = get_arg("user_id")
            if user_id is None:
                raise MissingInformation("user_id")
        else:
            user_id = None
    except MissingInformation as e:
        return make_error(e.message)

    try:
        if user_id is None:
            user_id = get_user_id_from_token(token)
    except InvalidInformation as e:
        return make_error(e.message)

    conn = engine.connect()
    query = sql.select([Subscription.level_id])\
        .where(Subscription.user_id == user_id)\
        .limit(50)

    res = conn.execute(query)

    return ",".join(str(row["level_id"]) for row in res.fetchall())



if __name__ == "__main__":
    context = ("server.crt", "server.key")
    app.run("0.0.0.0", ssl_context=context)