# main.py

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.core.image import Image as CoreImage
import cv2
import numpy as np
import base64
import easyocr
import requests
import threading
import os
from io import BytesIO

class CaptchaApp(BoxLayout):
    def __init__(self, **kwargs):
        super(CaptchaApp, self).__init__(**kwargs)
        self.orientation = 'vertical'
        self.accounts = {}
        self.background_images = []
        self.last_status_code = None
        self.last_response_text = None
        self.reader = easyocr.Reader(['en'], gpu=False, model_storage_directory=os.path.join(os.getcwd(), "model"))
        self.corrections = self.load_corrections()

        # UI Elements
        self.username_label = Label(text='Enter Username')
        self.username_input = TextInput()
        self.add_widget(self.username_label)
        self.add_widget(self.username_input)

        self.password_label = Label(text='Enter Password')
        self.password_input = TextInput(password=True)
        self.add_widget(self.password_label)
        self.add_widget(self.password_input)

        self.add_button = Button(text='Add Account')
        self.add_button.bind(on_press=self.add_account)
        self.add_widget(self.add_button)

        self.upload_button = Button(text='Upload Backgrounds')
        self.upload_button.bind(on_press=self.upload_backgrounds)
        self.add_widget(self.upload_button)

    def upload_backgrounds(self, instance):
        # Functionality to upload and process background images
        pass  # Placeholder for actual functionality

    def add_account(self, instance):
        username = self.username_input.text
        password = self.password_input.text
        if username and password:
            threading.Thread(target=self.async_add_account, args=(username, password)).start()

    def async_add_account(self, username, password):
        # Here you would add your logic to handle login and captcha
        print(f"Adding account for user {username}")
        user_agent = self.generate_user_agent()
        session = requests.Session()
        session.headers.update(self.generate_headers(user_agent))

        if self.login(username, password, session):
            self.accounts[username] = {
                'password': password,
                'user_agent': user_agent,
                'session': session,
                'captcha_id1': None,
                'captcha_id2': None
            }
            self.create_account_ui(username)
        else:
            self.show_popup("Error", f"Failed to login for user {username}")

    def create_account_ui(self, username):
        # Create UI for each account
        account_label = Label(text=f"Account: {username}")
        self.add_widget(account_label)
        # More UI components for captcha interaction

    def login(self, username, password, session):
        # Simulated login function; replace with actual request logic
        login_url = 'https://api.ecsc.gov.sy:8080/secure/auth/login'
        login_data = {'username': username, 'password': password}
        try:
            response = session.post(login_url, json=login_data)
            if response.status_code == 200:
                return True
            else:
                self.last_status_code = response.status_code
                self.last_response_text = response.text
                return False
        except Exception as e:
            self.show_popup("Error", f"Login request failed: {e}")
            return False

    def request_captcha(self, username, captcha_id):
        session = self.accounts[username].get('session')
        if not session:
            self.show_popup("Error", f"No session found for user {username}")
            return

        threading.Thread(target=self.async_request_captcha, args=(username, captcha_id, session)).start()

    def async_request_captcha(self, username, captcha_id, session):
        # Request and process captcha here
        pass  # Placeholder for actual captcha processing logic

    def show_captcha(self, captcha_data, username, captcha_id):
        # Function to display captcha image and handle input
        pass  # Placeholder for captcha display logic

    def process_captcha(self, captcha_image):
        # Image processing using OpenCV
        pass  # Placeholder for image processing logic

    def submit_captcha(self, username, captcha_id, captcha_solution):
        session = self.accounts[username].get('session')
        if not session:
            self.show_popup("Error", f"No session found for user {username}")
            return

        threading.Thread(target=self.async_submit_captcha, args=(username, captcha_id, captcha_solution, session)).start()

    def async_submit_captcha(self, username, captcha_id, captcha_solution, session):
        # Submit captcha solution to server
        pass  # Placeholder for actual submission logic

    @staticmethod
    def generate_headers(user_agent):
        return {
            'User-Agent': user_agent,
            'Content-Type': 'application/json',
            'Source': 'WEB',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://ecsc.gov.sy/',
            'Origin': 'https://ecsc.gov.sy',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site'
        }

    @staticmethod
    def generate_user_agent():
        user_agent_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv=89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15"
        ]
        return random.choice(user_agent_list)

    def load_corrections(self):
        # Load corrections from file
        file_path = os.path.join(os.getcwd(), "corrections.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def show_popup(self, title, message):
        popup = Popup(title=title, content=Label(text=message), size_hint=(None, None), size=(400, 200))
        popup.open()

class MyApp(App):
    def build(self):
        return CaptchaApp()

if __name__ == '__main__':
    MyApp().run()
