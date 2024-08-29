import base64
import random
import time
import asyncio
import threading
import flet as ft
import cv2
import numpy as np
from PIL import Image
import httpx
import easyocr
import re
import json
import os
from io import BytesIO

# تحسين إعدادات EasyOCR لتسريع العملية
reader = easyocr.Reader(['en'], gpu=True, model_storage_directory=os.path.join(os.getcwd(), "model"), download_enabled=True)

class CaptchaApp(ft.UserControl):
    def __init__(self):
        super().__init__()
        self.accounts = {}
        self.background_images = []
        self.last_status_code = None
        self.last_response_text = None
        self.corrections = self.load_corrections()

    def build(self):
        """Build the main user interface with Flet components."""
        self.account_column = ft.Column()
        
        self.add_account_button = ft.ElevatedButton(text="Add Account", on_click=self.add_account)
        self.upload_background_button = ft.ElevatedButton(text="Upload Backgrounds", on_click=self.upload_backgrounds)

        return ft.Column([
            self.add_account_button,
            self.upload_background_button,
            self.account_column
        ])

    async def upload_backgrounds(self, e):
        """Upload background images for processing."""
        background_files = await self.page.dialog_get_open_files(allowed_extensions=["jpg", "png", "jpeg"])
        if background_files:
            self.background_images = [cv2.imread(file.path) for file in background_files]
            ft.MessageDialog(title="Success", content=f"{len(self.background_images)} background images uploaded successfully!").open()

    def add_account(self, e):
        """Add a new account for captcha solving."""
        async def async_add_account():
            username = await self.page.dialog_get_input(title="Enter Username")
            password = await self.page.dialog_get_input(title="Enter Password", password=True)

            if username and password:
                user_agent = self.generate_user_agent()
                session = self.create_session(user_agent)
                if await self.login(username, password, session):
                    self.accounts[username] = {
                        'password': password,
                        'user_agent': user_agent,
                        'session': session,
                        'captcha_id1': None,
                        'captcha_id2': None
                    }
                    self.create_account_ui(username)
                else:
                    ft.MessageDialog(title="Error", content=f"Failed to login for user {username}").open()

        asyncio.create_task(async_add_account())

    def create_account_ui(self, username):
        """Create the UI elements for a specific account."""
        account_row = ft.Row()
        account_row.controls.append(ft.Text(f"Account: {username}"))

        captcha_id1 = ft.TextField(label="Captcha ID 1", on_submit=lambda e: self.update_captcha_id(username, e.control.value, 'captcha_id1'))
        captcha_id2 = ft.TextField(label="Captcha ID 2", on_submit=lambda e: self.update_captcha_id(username, e.control.value, 'captcha_id2'))
        
        account_row.controls.append(captcha_id1)
        account_row.controls.append(captcha_id2)

        cap1_button = ft.ElevatedButton(text="Cap 1", on_click=lambda e: self.request_captcha(username, captcha_id1.value))
        cap2_button = ft.ElevatedButton(text="Cap 2", on_click=lambda e: self.request_captcha(username, captcha_id2.value))
        request_all_button = ft.ElevatedButton(text="Request All", on_click=lambda e: self.request_all_captchas(username))
        
        account_row.controls.append(cap1_button)
        account_row.controls.append(cap2_button)
        account_row.controls.append(request_all_button)

        self.account_column.controls.append(account_row)
        self.update()

    def update_captcha_id(self, username, value, captcha_key):
        """Update captcha IDs in the account dictionary."""
        self.accounts[username][captcha_key] = value

    def request_all_captchas(self, username):
        """Request all captchas for the specified account."""
        self.request_captcha(username, self.accounts[username]['captcha_id1'])
        self.request_captcha(username, self.accounts[username]['captcha_id2'])

    @staticmethod
    def create_session(user_agent):
        """Create an HTTP session with custom headers."""
        return httpx.Client(headers=CaptchaApp.generate_headers(user_agent))

    async def login(self, username, password, session, retry_count=3):
        """Attempt to log in to the account."""
        login_url = 'https://api.ecsc.gov.sy:8080/secure/auth/login'
        login_data = {'username': username, 'password': password}

        for attempt in range(retry_count):
            try:
                print(f"Attempt {attempt + 1} to log in for user {username}")
                response = await session.post(login_url, json=login_data)
                print(f"HTTP Status Code: {response.status_code}")
                print(f"Response Text: {response.text}")

                if response.status_code == 200:
                    return True
                elif response.status_code in {401, 402, 403}:
                    ft.MessageDialog(title="Error", content=f"Error {response.status_code}. Retrying...").open()
                else:
                    print(f"Unexpected error code: {response.status_code}")
                    return False
            except httpx.RequestError as e:
                print(f"Request error: {e}")
                ft.MessageDialog(title="Error", content=f"Request error: {e}. Retrying...").open()
            except httpx.HTTPStatusError as e:
                print(f"HTTP status error: {e}")
                ft.MessageDialog(title="Error", content=f"HTTP status error: {e}. Retrying...").open()
            except Exception as e:
                print(f"Unexpected error: {e}")
                ft.MessageDialog(title="Error", content=f"Unexpected error: {e}. Retrying...").open()
            await asyncio.sleep(2)
        return False

    def request_captcha(self, username, captcha_id):
        """Request a captcha image for processing."""
        session = self.accounts[username].get('session')
        if not session:
            ft.MessageDialog(title="Error", content=f"No session found for user {username}").open()
            return

        # Send OPTIONS request before the GET request
        async def async_request_captcha():
            try:
                options_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha=0"
                await session.options(options_url)
            except httpx.RequestError as e:
                ft.MessageDialog(title="Error", content=f"Failed to send OPTIONS request: {e}").open()
                return

            # Send GET request to retrieve the captcha image
            captcha_data = await self.get_captcha(session, captcha_id)
            if captcha_data:
                self.show_captcha(captcha_data, username, captcha_id)
            else:
                if self.last_status_code == 403:  # Session expired
                    ft.MessageDialog(title="Session expired", content=f"Session expired for user {username}. Re-logging in...").open()
                    if await self.login(username, self.accounts[username]['password'], session):
                        ft.MessageDialog(title="Re-login successful", content=f"Re-login successful for user {username}. Please request the captcha again.").open()
                    else:
                        ft.MessageDialog(title="Re-login failed", content=f"Re-login failed for user {username}. Please check credentials.").open()
                else:
                    ft.MessageDialog(title="Error", content=f"Failed to get captcha. Status code: {self.last_status_code}, Response: {self.last_response_text}").open()

        asyncio.create_task(async_request_captcha())

    async def get_captcha(self, session, captcha_id):
        """Retrieve the captcha image data."""
        try:
            captcha_url = f"https://api.ecsc.gov.sy:8080/files/fs/captcha/{captcha_id}"
            response = await session.get(captcha_url)

            self.last_status_code = response.status_code
            self.last_response_text = response.text

            if response.status_code == 200:
                response_data = response.json()
                return response_data.get('file')
        except Exception as e:
            ft.MessageDialog(title="Error", content=f"Failed to get captcha: {e}").open()
        return None

    def show_captcha(self, captcha_data, username, captcha_id):
        """Display the captcha image for user input using Flet."""
        async def async_show_captcha():
            try:
                captcha_base64 = captcha_data.split(",")[1] if ',' in captcha_data else captcha_data
                captcha_image_data = base64.b64decode(captcha_base64)

                with open("captcha.jpg", "wb") as f:
                    f.write(captcha_image_data)

                captcha_image = cv2.imread("captcha.jpg")
                processed_image = self.process_captcha(captcha_image)

                # Resize the image to 110x60
                processed_image = cv2.resize(processed_image, (110, 60))

                # Convert all black pixels to white
                processed_image[np.all(processed_image == [0, 0, 0], axis=-1)] = [255, 255, 255]

                # Convert processed image to Flet Image format
                _, encoded_image = cv2.imencode('.jpg', processed_image)
                captcha_image_flet = ft.Image(src_base64=base64.b64encode(encoded_image).decode('utf-8'))

                # Now perform OCR processing
                img_array = np.array(processed_image)
                
                # تحسين الأداء من خلال تحديد أقصى عدد للأحرف المراد التعرف عليها
                predictions = reader.readtext(img_array, detail=0, allowlist='0123456789+-*/')

                # Correct the OCR output with our custom function
                corrected_text, highlighted_image = self.correct_and_highlight(predictions, img_array)

                captcha_solution = self.solve_captcha(corrected_text)

                ocr_output_text = ft.TextField(value=corrected_text, label="OCR Output")
                captcha_entry = ft.TextField(value=captcha_solution, label="Captcha Input")

                submit_button = ft.ElevatedButton(
                    text="Submit Captcha",
                    on_click=lambda e: self.submit_captcha(username, captcha_id, captcha_entry.value)
                )

                self.page.controls.append(ft.Column([
                    captcha_image_flet,
                    ocr_output_text,
                    captcha_entry,
                    submit_button
                ]))
                self.update()

            except Exception as e:
                ft.MessageDialog(title="Error", content=f"Failed to show captcha: {e}").open()

        asyncio.create_task(async_show_captcha())

    def process_captcha(self, captcha_image):
        """Apply advanced image processing to remove the background using added backgrounds while keeping original colors."""
        # Resize the image to 110x60
        captcha_image = cv2.resize(captcha_image, (110, 60))

        if not self.background_images:
            return captcha_image

        # Initialize variables for the best match
        best_background = None
        min_diff = float('inf')

        # Find the best matching background
        for background in self.background_images:
            # Resize background to match the captcha image size
            background = cv2.resize(background, (110, 60))

            # Apply the background removal logic
            processed_image = self.remove_background_keep_original_colors(captcha_image, background)

            # Evaluate the result
            gray_diff = cv2.cvtColor(processed_image, cv2.COLOR_BGR2GRAY)
            score = np.sum(gray_diff)

            if score < min_diff:
                min_diff = score
                best_background = background

        if best_background is not None:
            # Apply background removal with the best matched background
            cleaned_image = self.remove_background_keep_original_colors(captcha_image, best_background)
            return cleaned_image
        else:
            return captcha_image

    @staticmethod
    def remove_background_keep_original_colors(captcha_image, background_image):
        """Remove background from captcha image while keeping the original colors of elements."""
        if background_image.shape != captcha_image.shape:
            background_image = cv2.resize(background_image, (captcha_image.shape[1], captcha_image.shape[0]))

        # Calculate the difference between the captcha image and the background
        diff = cv2.absdiff(captcha_image, background_image)

        # Convert the difference to grayscale to create a mask
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

        # Set the threshold to create a mask that highlights differences
        _, mask = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

        # Apply the mask to the captcha image to keep original colors
        result = cv2.bitwise_and(captcha_image, captcha_image, mask=mask)

        return result

    def submit_captcha(self, username, captcha_id, captcha_solution):
        """Submit the captcha solution to the server."""
        session = self.accounts[username].get('session')
        if not session:
            ft.MessageDialog(title="Error", content=f"No session found for user {username}").open()
            return

        # Send OPTIONS request before the GET request
        async def async_submit_captcha():
            try:
                options_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha={captcha_solution}"
                await session.options(options_url)
            except httpx.RequestError as e:
                ft.MessageDialog(title="Error", content=f"Failed to send OPTIONS request: {e}").open()
                return

            # Send GET request to submit the captcha solution
            try:
                get_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha={captcha_solution}"
                response = await session.get(get_url)

                if response.status_code == 200:
                    response_data = response.json()
                    if 'message' in response_data:
                        ft.MessageDialog(title="Success", content=response_data['message']).open()
                    else:
                        ft.MessageDialog(title="Success", content="Captcha submitted successfully!").open()
                else:
                    ft.MessageDialog(title="Error", content=f"Failed to submit captcha. Status code: {response.status_code}, Response: {response.text}").open()

            except Exception as e:
                ft.MessageDialog(title="Error", content=f"Failed to submit captcha: {e}").open()

        asyncio.create_task(async_submit_captcha())

    @staticmethod
    def generate_headers(user_agent):
        """Generate HTTP headers for the session."""
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
        """Generate a random user agent string."""
        user_agent_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv=89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/13.1.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/56.0.2924.87 Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/47.0.2526.106 Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36"
        ]
        
        return random.choice(user_agent_list)

    def correct_and_highlight(self, predictions, image):
        """Correct OCR predictions and apply color highlights to numbers and operators."""
        corrections = {
            'O': '0', 'S': '5', 'I': '1', 'B': '8', 'G': '6',
            'Z': '2', 'T': '7', 'A': '4', 'X': '*', '×': '*', 'L': '1',
            'H': '8', '_': '-', '/': '7', '£': '8', '&': '8'
        }

        # Prepare to highlight extracted numbers and operators in different colors
        num_color = (0, 255, 0)  # Green for numbers
        op_color = (0, 0, 255)  # Red for operators
        corrected_text = ""
        
        for text in predictions:
            text = text.strip().upper()
            for char in text:
                corrected_char = corrections.get(char, char)
                if corrected_char.isdigit():
                    corrected_text += corrected_char
                elif corrected_char in "+-*xX×":
                    corrected_text += corrected_char
                else:
                    corrected_text += corrected_char  # Non-highlighted

        return corrected_text, image

    def learn_from_correction(self, original_text, corrected_text):
        """Learn from user correction and store the correction in a file."""
        if original_text != corrected_text:
            self.corrections[original_text] = corrected_text
            self.save_corrections()

    def save_corrections(self):
        """Save corrections to a file on the desktop."""
        file_path = os.path.join(r"C:\Users\Gg\Desktop", "corrections.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.corrections, f, ensure_ascii=False, indent=4)

    def load_corrections(self):
        """Load corrections from a file on the desktop."""
        file_path = os.path.join(r"C:\Users\Gg\Desktop", "corrections.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    @staticmethod
    def solve_captcha(corrected_text):
        """Solve the captcha by extracting two numbers and one operator."""
        corrected_text = re.sub(r"[._/]", "", corrected_text)  # Remove any ambiguous marks for clarity

        # Extract numbers and operators
        numbers = re.findall(r'\d+', corrected_text)
        operators = re.findall(r'[+*xX-]', corrected_text)

        if len(numbers) == 2 and len(operators) == 1:
            num1, num2 = map(int, numbers)
            operator = operators[0]

            if operator in ['*', '×', 'x']:
                return abs(num1 * num2)
            elif operator == '+':
                return abs(num1 + num2)
            elif operator == '-':
                return abs(num1 - num2)

        # Handle cases like `-86` as `8-6`
        if len(corrected_text) == 3 and corrected_text[0] in {'+', '-', '*', 'x', '×'}:
            num1, operator, num2 = corrected_text[1], corrected_text[0], corrected_text[2]
            num1, num2 = int(num1), int(num2)

            if operator in ['*', '×', 'x']:
                return abs(num1 * num2)
            elif operator == '+':
                return abs(num1 + num2)
            elif operator == '-':
                return abs(num1 - num2)

        return None

def main(page):
    app = CaptchaApp()
    page.add(app)

if __name__ == "__main__":
    ft.app(target=main)
