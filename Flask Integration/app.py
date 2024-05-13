import os
import pathlib
from dotenv import load_dotenv 
load_dotenv()
from flask import Flask, session, abort, redirect, request, render_template
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
import numpy as np
import pickle
import time
import requests
import datetime
from datetime import date

#Function to get age from birthday
def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

#Function to get current time in milliseconds
def current_milli_time():
    return round(time.time() * 1000)

#Function to check if user is logged in
def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return abort(401)  # Authorization required
        else:
            return function()
    return wrapper

#Function to get user data according to the datatype
def get_user_data(access_token, data_type_name, start_time_millis, end_time_millis):
    headers = {'Authorization': f'Bearer {access_token}'}
    request_body = {
        "aggregateBy": [{
            "dataTypeName": data_type_name
        }],
        "bucketByTime": { "durationMillis": 86400000 },  # Aggregate by day
        "startTimeMillis": start_time_millis,
        "endTimeMillis": end_time_millis
    }
    response = requests.post('https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate', headers=headers, json=request_body)
    user_data = response.json()
    return user_data


#Function to get gender and birthday
def get_age_gender(access_token):
    personData = requests.get("https://people.googleapis.com/v1/people/me?personFields=genders,birthdays",
                              headers={'Authorization': f'Bearer {access_token}'})
    user_data = personData.json()
    return user_data

#Function to get sleep data
def get_sleep_data(access_token, start_time_millis, end_time_millis):
    headers = {'Authorization': f'Bearer {access_token}'}

    start = str(datetime.datetime.fromtimestamp(start_time_millis/1000.0))[:-3]
    end = str(datetime.datetime.fromtimestamp(end_time_millis/1000.0))[:-3]
    response = requests.get('https://www.googleapis.com/fitness/v1/users/me/sessions?startTimeMillis='
                            +str(start_time_millis)+'&endTimeMillis='+str(end_time_millis)+'&activityType=72',headers=headers)
    user_data = response.json()
    return user_data

def warn(*args, **kwargs):
    pass
import warnings
warnings.warn = warn

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/user.gender.read",
            "https://www.googleapis.com/auth/user.birthday.read",
            "https://www.googleapis.com/auth/fitness.activity.read",
            "https://www.googleapis.com/auth/fitness.blood_pressure.read",
            "https://www.googleapis.com/auth/fitness.body.read",
            "https://www.googleapis.com/auth/fitness.heart_rate.read",
            "https://www.googleapis.com/auth/fitness.sleep.read",
            ],
    redirect_uri="http://127.0.0.1:5000/callback"
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
root = os.path.dirname(__file__)

#Open pickle files and load them 
with open(root+'\models\ensemble_heart.pickle', 'rb') as f:
    ensem = pickle.load(f)

with open(root+'\models\standardScaler.pickle', 'rb') as f:
    std = pickle.load(f)

with open(root+'\models\Scale_sleep2.pickle', 'rb') as f:
    scl_sleep = pickle.load(f)

with open(root+'\models\ensemble_sleep2.pickle2', 'rb') as f:
    ensem_sleep = pickle.load(f)


# Function to predict heart disease
def predict_disease(input_data, std_scale, model):
    # Reshape input data
    input_data_array = np.asarray(input_data)
    input_data_reshaped = input_data_array.reshape(1, -1)
    scaled_data = std_scale.transform(input_data_reshaped)
    # Make prediction
    prediction = model.predict(scaled_data)
    return prediction

@app.route('/')
def landing():
   return render_template('login.html')

@app.route("/login")
def login():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

#Callback function
@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)

    if not session["state"] == request.args["state"]:
        abort(500)  #State does not match!

    credentials = flow.credentials
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)

    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID,
        clock_skew_in_seconds=5
    )

    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    session["pfp"] = id_info.get("picture")
    session["google_id_token"] = credentials._id_token
    session["google_credentials"] = credentials.to_json()
    session["google_access_token"] = credentials.token
    return redirect("/data")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route('/data')
@login_is_required
def data_acq():
    access_token = session.get("google_access_token")

    sevenDaysInMillis = 7 * 24 * 60 * 60 * 1000
    startTimeMillis = current_milli_time() - sevenDaysInMillis
    endTimeMillis = current_milli_time()

    session['age'] = ""
    session['gender'] = ""
    session['avgsteps'] = ""
    session['max_heart'] = ""
    session['systolic'] = ""
    session['diastolic'] = ""
    session['sleep_hours'] = ""

    #check if logged in
    if access_token:
        age_gender = get_age_gender(access_token)
        birthday = datetime.date(age_gender['birthdays'][0]['date']['year'],age_gender['birthdays'][0]['date']['month'],age_gender['birthdays'][0]['date']['day'])
        age = calculate_age(birthday)
        gender = age_gender['genders'][0]['value']

        session['age'] = age
        session['gender'] = gender
        
        steps_data = get_user_data(access_token, 'com.google.step_count.delta', startTimeMillis, endTimeMillis)
        heart_rate_data = get_user_data(access_token, 'com.google.heart_rate.bpm', startTimeMillis, endTimeMillis)
        bp_data = get_user_data(access_token, 'com.google.blood_pressure', startTimeMillis, endTimeMillis)
        sleep_data = get_sleep_data(access_token, startTimeMillis, endTimeMillis)
        
        #Check if user has the respective data
        if steps_data:
            steps = []
            avg_steps = 0
            for i in steps_data["bucket"]:
                if i["dataset"][0]["point"]:
                    step = i["dataset"][0]["point"][0]["value"][0]["intVal"]
                    steps.append(step)
            if steps:
                avg_steps = (sum(steps)//len(steps))
            session['avgsteps'] = avg_steps
        # print(steps_data)
        
        if heart_rate_data:
            maxheart = []
            avgheart = []
            max_rate = 0
            avg_rate = 0
            for i in heart_rate_data["bucket"]: 
                if i["dataset"][0]["point"]:
                    avgrate = i["dataset"][0]["point"][0]["value"][0]["fpVal"]
                    maxrate = i["dataset"][0]["point"][0]["value"][1]["fpVal"]
                    avgheart.append(avgrate)
                    maxheart.append(maxrate)
            if avgheart and maxheart:
                max_rate = max(maxheart)
                avg_rate = (sum(avgheart)//len(avgheart))
            session['max_heart'] = int(max_rate)
            session['avg_heart'] = int(avg_rate)
        # print(heart_rate_data)
        
        if bp_data:
            systolic = []
            diastolic = []
            sys_avg = 0
            dia_avg = 0
            for i in bp_data["bucket"]:
                if i["dataset"][0]["point"]:
                    sys = i["dataset"][0]["point"][0]["value"][0]["fpVal"]
                    dia = i["dataset"][0]["point"][0]["value"][3]["fpVal"]
                    systolic.append(sys)
                    diastolic.append(dia)
            if systolic and diastolic:
                sys_avg = (sum(systolic)//len(systolic))
                dia_avg = (sum(diastolic)//len(diastolic))
            session['systolic'] = int(sys_avg)
            session['diastolic'] = int(dia_avg)
        # print(bp_data)

        if sleep_data['session']:
            sleep = []
            for i in sleep_data["session"]:
                    start = int(i["startTimeMillis"])
                    end = int(i["endTimeMillis"])
                    total = end - start
                    hours = round(total/3600000,2)
                    sleep.append(hours)
            if sleep:
                sleep_hours = (sum(sleep)//len(sleep))
            session['sleep_hours'] = sleep_hours
        # print(sleep_data)

        return redirect("/homepage")
    else:
        return "No Fit API access token found. Please authenticate first."
    
@app.route('/homepage')
def homepage():
    if session.get("google_access_token"):
        return render_template("homepage.html", name=session['name'], pfp=session['pfp'])
    else:
        return render_template("homepage.html")

@app.route('/heart')
def heart():
   if session.get("google_access_token"):
    age = session['age']
    gender = session['gender']
    bp = session['systolic']
    rate = session['max_heart']
    return render_template('heartattack.html',age=age, gender=gender, bp=bp, rate=rate)
   else:
    return render_template('heartattack.html')


@app.route('/sleep')
def sleep():
   if session.get("google_access_token"):
    gender = session['gender']
    age = session['age']
    systolic = session['systolic']
    diastolic = session['diastolic']
    steps = session['avgsteps']
    rate = session['avg_heart']
    sleepdura = session['sleep_hours']
    return render_template('sleepdisorder.html',gender=gender, steps=steps, age=age, systolic=systolic, diastolic=diastolic, rate=rate, sleepdura=sleepdura)
   else:
    return render_template('sleepdisorder.html')

@app.route('/hrisk', methods = ['POST','GET'])
def hrisk():
    if request.method == 'POST':
        try:
            age = int(request.form['age'])
            gender = request.form['gender']
            rbp = int(request.form['rbp'])
            chol = int(request.form['chol'])
            fbs = int(request.form['sugar'])
            ecg = int(request.form['ecg'])
            rate = int(request.form['rate'])
            ang = int(request.form['ang'])
            thal = int(request.form['thal'])

            gender = 1 if gender == "male" else 0
            input_data = (age,gender,rbp,chol,fbs,ecg,rate,ang,thal)
            # print(input_data)

            prediction = predict_disease(input_data, std, ensem)
            if prediction[0] == 0:
                return render_template("heartattack.html", risk="You have a healthy heart!")
            else:
                return render_template("heartattack.html", risk="You're at risk of getting a heart attack!")

        except:
            print("Error")

# @app.route('/process', methods=['POST']) 
# def process(): 
#     data = request.get_json()
#     result = tuple(data['list'])
#     print(type(result))
#     prediction = predict_disease(result, std, ensem)
#     risk = ""
#     if prediction[0] == 0:
#         risk = "No"
#     else:
#         risk = "Yes"
#     return jsonify(result=risk)

@app.route('/srisk', methods = ['POST','GET'])
def srisk():
    if request.method == 'POST':

            gender = request.form['gender']
            age = int(request.form['age'])
            sleepdura = float(request.form['sleepdura'])
            phys = int(request.form['phys'])
            stress = int(request.form['stress'])
            bmi = int(request.form['bmi'])
            rate = int(request.form['rate'])
            step = int(request.form['step'])
            sys = int(request.form['sys'])
            dia = int(request.form['dia'])
            
            gender = 1 if gender == "male" else 0
            input_data = (gender,bmi,sys,dia,age,sleepdura,phys,stress,rate,step)
            prediction = predict_disease(input_data, scl_sleep, ensem_sleep)
            if prediction[0] == 0:
                return render_template("sleepdisorder.html", risk="Safe from any sleeping disorders!")
            elif prediction[0] == 1:
                return render_template("sleepdisorder.html", risk="Risk of Sleep Apnea")
            else:
                return render_template("sleepdisorder.html", risk="Risk of Insomnia")


if __name__ == '__main__':
   app.run(debug = True)
