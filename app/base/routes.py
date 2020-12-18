# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from flask import jsonify, render_template, redirect, request, url_for
from flask import current_app
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user
)

from app import db, mysql, login_manager
from app.base import blueprint
from app.base.forms import LoginForm, CreateAccountForm
from app.base.models import PushSubscription, User

from app.base.util import verify_pass
from app.base.webpush_handler import trigger_push_notifications_for_subscriptions

from twilio.rest import Client
import requests
import json
from collections import OrderedDict

base_url = "http://127.0.0.1:10027"


@blueprint.route('/')
def route_default():
    return redirect(url_for('base_blueprint.login'))

# Login & Registration


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    login_form = LoginForm(request.form)
    if 'login' in request.form:

        # read form data
        username = request.form['username']
        password = request.form['password']

        # Locate user
        user = User.query.filter_by(username=username).first()

        # Check the password
        if user and verify_pass(password, user.password):

            login_user(user)
            return redirect(url_for('base_blueprint.route_default'))

        # Something (user or pass) is not ok
        return render_template('accounts/login.html', msg='Wrong user or password', form=login_form)

    if not current_user.is_authenticated:
        return render_template('accounts/login.html',
                               form=login_form)
    return redirect(url_for('home_blueprint.index'))


@blueprint.route('/register', methods=['GET', 'POST'])
def register():
    login_form = LoginForm(request.form)
    create_account_form = CreateAccountForm(request.form)
    if 'register' in request.form:

        username = request.form['username']
        email = request.form['email']

        # Check usename exists
        user = User.query.filter_by(username=username).first()
        if user:
            return render_template('accounts/register.html',
                                   msg='Username already registered',
                                   success=False,
                                   form=create_account_form)

        # Check email exists
        user = User.query.filter_by(email=email).first()
        if user:
            return render_template('accounts/register.html',
                                   msg='Email already registered',
                                   success=False,
                                   form=create_account_form)

        # else we can create the user
        user = User(**request.form)
        db.session.add(user)
        db.session.commit()

        return render_template('accounts/register.html',
                               msg='User created please <a href="/login">login</a>',
                               success=True,
                               form=create_account_form)

    else:
        return render_template('accounts/register.html', form=create_account_form)


@blueprint.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('base_blueprint.login'))


@blueprint.route('/shutdown')
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'

# Errors


@login_manager.unauthorized_handler
def unauthorized_handler():
    return render_template('page-403.html'), 403


@blueprint.errorhandler(403)
def access_forbidden(error):
    return render_template('page-403.html'), 403


@blueprint.errorhandler(404)
def not_found_error(error):
    return render_template('page-404.html'), 404


@blueprint.errorhandler(500)
def internal_error(error):
    return render_template('page-500.html'), 500

# API


@blueprint.route('/admin-api/get-graph-data', methods=['GET'])
def get_graph_data():
    conn = mysql.connect()
    curs = conn.cursor()
    query = "SELECT Heart_Rate, Temperature, Humidity FROM Sensor_Data ORDER BY Sensor_Sequence DESC LIMIT 6"
    curs.execute(query)
    rows = curs.fetchall()
    objects_list = []
    for row in rows:
        d = OrderedDict()
        d["Heart_Rate"] = row[0]
        d["Temperature"] = row[1]
        d["Humidity"] = row[2]
        objects_list.append(d)
    conn.close()

    return jsonify(objects_list)


@blueprint.route('/admin-api/get-table-data', methods=['GET'])
def get_table_data():
    conn = mysql.connect()
    curs = conn.cursor()
    query = "SELECT User.Name, Emergency_Record.Time, Emergency_Record.Description FROM User, Emergency_Record WHERE User.MAC_Address = Emergency_Record.MAC_Address ORDER BY Emergency_Record.Emergency_ID DESC"
    curs.execute(query)
    rows = curs.fetchall()
    objects_list = []
    for row in rows:
        d = OrderedDict()
        d["Name"] = row[0]
        d["Time"] = row[1]
        d["Description"] = row[2]
        objects_list.append(d)
    conn.close()

    return jsonify(objects_list)


@blueprint.route('/admin-api/get-table-data-2', methods=['GET'])
def get_table_data_2():
    conn = mysql.connect()
    curs = conn.cursor()
    query_1 = "SELECT Name, MAC_Address FROM User"
    curs.execute(query_1)
    rows = curs.fetchall()
    user_data = [row for row in rows]
    objects_list = []

    for user in user_data:
        mac = user[1]
        query_2 = "select Heart_Rate, Temperature, Humidity from Sensor_Data WHERE MAC_Address = '{}' order by Sensor_Sequence DESC limit 1".format(
            mac)
        curs.execute(query_2)
        row = curs.fetchone()
        d = OrderedDict()
        d["Name"] = user[0]
        d["Heart_Rate"] = row[0]
        d["Temperature"] = row[1]
        d["Humidity"] = row[2]
        objects_list.append(d)
    conn.close()

    return jsonify(objects_list)


@blueprint.route('/admin-api/push-subscriptions', methods=['POST'])
def create_push_subscription():
    json_data = request.get_json()
    subscription = PushSubscription.query.filter_by(
        subscription_json=json_data['subscription_json']
    ).first()
    if subscription is None:
        subscription = PushSubscription(
            subscription_json=json_data['subscription_json']
        )
        db.session.add(subscription)
        db.session.commit()

    return jsonify({
        "status": "success",
        "result": {
            "id": subscription.id,
            "subscription_json": subscription.subscription_json
        }
    })


@blueprint.route('/admin-api/trigger-push-notifications', methods=['POST'])
def trigger_push_notifications():
    json_data = request.get_json(force=True)
    subscriptions = PushSubscription.query.all()
    results = trigger_push_notifications_for_subscriptions(
        subscriptions,
        json_data.get('title'),
        json_data.get('body')
    )

    return jsonify({
        "status": "success",
        "result": results
    })


@blueprint.route('/admin-api/send-messages', methods=['POST'])
def send_messages():
    account_sid = current_app.config["TWILIO_ACCOUNT_SID"]
    auth_token = current_app.config["TWILIO_AUTH_TOKEN"]
    client = Client(account_sid, auth_token)

    from_ = current_app.config["TWILIO_FROM"]
    to = current_app.config["TWILIO_TO"]

    json_data = request.get_json(force=True)
    description = json_data.get('title') + '\n' + json_data.get('body')
    message = client.messages.create(
        body=description,
        from_=from_,
        to=to
    )

    return jsonify({
        "status": "success"
    })


@blueprint.route('/api/emergency/predict/server', methods=['POST'])
def predict():
    # get data
    _time = request.form['time']
    _mac = request.form['mac']
    _temp = request.form['temp']
    _hum = request.form['hum']
    _bio = request.form['bio']
    _pir = request.form['pir']
    _door = request.form['door']
    _fire = request.form['fire']
    _p_btn = request.form['p_btn']
    _in_house = request.form['in_house']

    emergency = False
    result = "Normal"
    conn = mysql.connect()
    curs = conn.cursor()

    sw = sleep_wake(curs)

    if int(_in_house) == 1:
        str_inHouse = "in"
    else:
        str_inHouse = "out"

    if sw:
        str_sw = "sleep"
    else:
        str_sw = "wake"

    print("inHouse = " + str_inHouse + ", sleepWake = " + str_sw)

    # TODO: emergency predict algorithm
    if int(_in_house) == 1:
        bio_predict1 = complicated_1(curs)
        bio_predict2 = complicated_2(curs, sw)
        if bio_predict1 or bio_predict2:
            emergency = True
            result = "Emergency"

    # TODO: 응급상황일때만 body 생성
    query = "SELECT Name FROM User WHERE MAC_Address = '{}'".format(_mac)
    curs.execute(query)
    user = curs.fetchone()[0]
    # user = ""
    body = "{}님: 응급상황 발생".format(user)

    # push notifications & send messages
    if emergency:
        emergency_push(body)
        # mysql insert emergency log
        curs.callproc('p_insert_emergency', (_time, body, _mac))
        conn.commit()

    # mysql insert data
    curs.callproc('p_insert_data', (_time, _mac, _temp,
                                    _hum, _bio, _pir, _door, _fire, _p_btn))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "result": result
    })


@blueprint.route('/api/emergency/predict/android', methods=['POST'])
def predict_android():
    # get data
    _time = request.form['time']
    _result = request.form['result']
    _mac = request.form['mac']

    # push notifications & send messages
    emergency_push(_result)

    # mysql insert emergency log
    conn = mysql.connect()
    curs = conn.cursor()
    curs.callproc('p_insert_emergency', (_time, _result, _mac))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success"
    })


@blueprint.route('/api/emergency/decision', methods=['POST'])
def predict_decision():
    # get data
    _time = request.form['time']
    _result = request.form['result']
    _mac = request.form['mac']

    # push notifications & send messages
    emergency_push(_result)

    # mysql insert emergency log
    conn = mysql.connect()
    curs = conn.cursor()
    curs.callproc('p_insert_emergency', (_time, _result, _mac))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success"
    })


def emergency_push(body):
    push_url = base_url + "/admin-api/trigger-push-notifications"
    requests.post(url=push_url, data=json.dumps(
        {"title": "응급상황이 발생했습니다.", "body": body}))
    send_url = base_url + "/admin-api/send-messages"
    requests.post(url=send_url, data=json.dumps(
        {"title": "응급상황이 발생했습니다.", "body": str(body)}))


def pir_0(pir_arr):
    cnt = 0
    for pir in pir_arr:
        if pir != 0:
            cnt += 1
    return cnt


def sleep_wake(curs):
    curs.execute(
        "SELECT Heart_Rate, PIR_Sensor FROM Sensor_Data ORDER BY Sensor_Sequence DESC limit 130")
    rows = curs.fetchall()
    show_sleep = [row[0] for row in rows]
    collect_pir = [row[1] for row in rows]

    # 대략 20분정도동안 132개의 pir값을 받는다. 132개가 모두 0이면 0, 0이 아닌숫자가 있으면 그걸 추가
    pir_cnt = pir_0(collect_pir)
    avg_sleep = sum(show_sleep)/len(show_sleep)
    if 40 <= avg_sleep <= 80 and pir_cnt == 0:
        return True
    return False


def complicated_1(curs):  # 집에 사람이 있는데 평균보다 심박수가 확느려지거나 빨리 뛸 때 위험예측
    curs.execute(
        "SELECT AVG(NULLIF(Heart_Rate,0)) FROM Sensor_Data ORDER BY Sensor_Sequence DESC limit 2000")
    bio_avg = curs.fetchone()[0]
    curs.execute(
        "SELECT Heart_Rate FROM Sensor_Data ORDER BY Sensor_Sequence DESC limit 6")
    rows = curs.fetchall()
    show_heart = [row[0] for row in rows]
    if 0 < min(show_heart) <= bio_avg - 15 or max(show_heart) >= bio_avg + 15:
        return True
    return False


def complicated_2(curs, sleep_wake):  # 취침시간인데 비정상적 심박수 + 취침시간아닌데 비정상적 심박수
    count = 0
    if sleep_wake is True:
        # 취침시간인데 비정상적 심박수
        low_bpm = 40
    else:
        # 일어나있는데 비정상적 심박수
        low_bpm = 60
    curs.execute(
        "SELECT Heart_Rate FROM Sensor_Data Order by Sensor_Sequence DESC limit 6")
    rows = curs.fetchall()
    show_heart = [row[0] for row in rows]
    for heart in show_heart:
        if (0 < heart <= low_bpm) or 80 <= heart:
            count += 1
    if count >= 2:
        return True
    return False
