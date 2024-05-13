import unittest
import io
from app import app, predict_disease, scl_sleep, ensem_sleep

class UnitTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

#Testing if the landing page gets loaded successfully
    def test_homepage(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

#Testing if login functions as expected   
    def test_login(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 302)
    
#Testing if the application gets logged out properly
    def test_logout(self):
        response = self.client.get('/logout')
        self.assertEqual(response.status_code, 302)

#Testing if the prediction is as expected
    def test_predict(self):
        gender = 1
        age = 21
        sleepdura = 9
        phys = 96
        stress = 7
        bmi = 1
        rate = 98
        step = 5025
        sys = 131
        dia = 98

        input_data = (gender,bmi,sys,dia,age,sleepdura,phys,stress,rate,step)
        prediction = predict_disease(input_data, scl_sleep, ensem_sleep)
        self.assertEqual(prediction, 1)

#Testing if the application gets logged out properly
    def test_heart_page(self):
        response = self.client.get('/heart')
        self.assertEqual(response.status_code, 200)