import base64
import random
import time
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox, Scrollbar, filedialog
import cv2
import numpy as np
from PIL import Image, ImageTk
import httpx
import easyocr
import re
import json
import os

# تحسين إعدادات EasyOCR لتسريع العملية
reader = easyocr.Reader(['en'], gpu=False, model_storage_directory=os.path.join(os.getcwd(), "model"), download_enabled=True)  # استخدام الـ CPU وتعطيل استخدام الـ GPU لتجنب تعطل الجهاز

class CaptchaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Captcha Solver")
        self.root.geometry("1000x600")

        self.accounts = {}
        self.background_images = []
        self.last_status_code = None
        self.last_response_text = None
        self.captcha_frame = None
        self.corrections = self.load_corrections()

        self.canvas = None
        self.scrollbar = None
        self.main_frame = None
        self.add_account_button = None
        self.upload_background_button = None

        self.setup_ui()

    def setup_ui(self):
        """Set up the main user interface."""
        self.canvas = tk.Canvas(self.root)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = Scrollbar(self.root, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.main_frame = tk.Frame(self.canvas)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas.create_window((0, 0), window=self.main_frame, anchor=tk.NW)
        self.main_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.create_widgets()

    def create_widgets(self):
        """Create UI widgets for user interactions."""
        self.add_account_button = tk.Button(self.main_frame, text="Add Account", command=self.add_account)
        self.add_account_button.pack()

        self.upload_background_button = tk.Button(
            self.main_frame, text="Upload Backgrounds", command=self.upload_backgrounds
        )
        self.upload_background_button.pack()

    def upload_backgrounds(self):
        """Upload background images for processing."""
        background_paths = filedialog.askopenfilenames(
            title="Select Background Images",
            filetypes=[("Image files", "*.jpg *.png *.jpeg")]
        )
        if background_paths:
            self.background_images = [cv2.imread(path) for path in background_paths]
            messagebox.showinfo("Success", f"{len(self.background_images)} background images uploaded successfully!")

    def add_account(self):
        """Add a new account for captcha solving."""
        username = simpledialog.askstring("Input", "Enter Username:")
        password = simpledialog.askstring("Input", "Enter Password:", show='*')

        if username and password:
            user_agent = self.generate_user_agent()
            session = self.create_session(user_agent)
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
                messagebox.showerror("Error", f"Failed to login for user {username}")

    def create_account_ui(self, username):
        """Create the UI elements for a specific account."""
        account_frame = tk.Frame(self.main_frame)
        account_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(account_frame, text=f"Account: {username}").pack(side=tk.LEFT)

        captcha_id1 = simpledialog.askstring("Input", "Enter Captcha ID 1:")
        captcha_id2 = simpledialog.askstring("Input", "Enter Captcha ID 2:")
        self.accounts[username]['captcha_id1'] = captcha_id1
        self.accounts[username]['captcha_id2'] = captcha_id2

        tk.Button(account_frame, text="Cap 1", command=lambda: threading.Thread(target=self.request_captcha, args=(username, captcha_id1)).start()).pack(
            side=tk.LEFT, padx=8
        )
        tk.Button(account_frame, text="Cap 2", command=lambda: threading.Thread(target=self.request_captcha, args=(username, captcha_id2)).start()).pack(
            side=tk.LEFT, padx=8
        )
        tk.Button(account_frame, text="Request All", command=lambda: threading.Thread(target=self.request_all_captchas, args=(username,)).start()).pack(
            side=tk.LEFT, padx=8
        )

    def request_all_captchas(self, username):
        """Request all captchas for the specified account."""
        self.request_captcha(username, self.accounts[username]['captcha_id1'])
        self.request_captcha(username, self.accounts[username]['captcha_id2'])

    @staticmethod
    def create_session(user_agent):
        """Create an HTTP session with custom headers."""
        return httpx.Client(headers=CaptchaApp.generate_headers(user_agent))

    def login(self, username, password, session, retry_count=3):
        """Attempt to log in to the account."""
        login_url = 'https://api.ecsc.gov.sy:8080/secure/auth/login'
        login_data = {'username': username, 'password': password}

        for attempt in range(retry_count):
            try:
                print(f"Attempt {attempt + 1} to log in for user {username}")
                response = session.post(login_url, json=login_data)
                print(f"HTTP Status Code: {response.status_code}")
                print(f"Response Text: {response.text}")

                if response.status_code == 200:
                    return True
                elif response.status_code in {401, 402, 403}:
                    messagebox.showerror("Error", f"Error {response.status_code}. Retrying...")
                else:
                    print(f"Unexpected error code: {response.status_code}")
                    return False
            except httpx.RequestError as e:
                print(f"Request error: {e}")
                messagebox.showerror("Error", f"Request error: {e}. Retrying...")
            except httpx.HTTPStatusError as e:
                print(f"HTTP status error: {e}")
                messagebox.showerror("Error", f"HTTP status error: {e}. Retrying...")
            except Exception as e:
                print(f"Unexpected error: {e}")
                messagebox.showerror("Error", f"Unexpected error: {e}. Retrying...")
            time.sleep(2)
        return False

    def request_captcha(self, username, captcha_id):
        """Request a captcha image for processing."""
        session = self.accounts[username].get('session')
        if not session:
            messagebox.showerror("Error", f"No session found for user {username}")
            return

        # Send OPTIONS request before the GET request
        try:
            options_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha=0"
            session.options(options_url)
        except httpx.RequestError as e:
            messagebox.showerror("Error", f"Failed to send OPTIONS request: {e}")
            return

        # Send GET request to retrieve the captcha image
        captcha_data = self.get_captcha(session, captcha_id)
        if captcha_data:
            self.show_captcha(captcha_data, username, captcha_id)
        else:
            if self.last_status_code == 403:  # Session expired
                messagebox.showinfo("Session expired", f"Session expired for user {username}. Re-logging in...")
                if self.login(username, self.accounts[username]['password'], session):
                    messagebox.showinfo("Re-login successful", f"Re-login successful for user {username}. Please request the captcha again.")
                else:
                    messagebox.showerror("Re-login failed", f"Re-login failed for user {username}. Please check credentials.")
            else:
                messagebox.showerror("Error", f"Failed to get captcha. Status code: {self.last_status_code}, "
                                              f"Response: {self.last_response_text}")

    def get_captcha(self, session, captcha_id):
        """Retrieve the captcha image data."""
        try:
            captcha_url = f"https://api.ecsc.gov.sy:8080/files/fs/captcha/{captcha_id}"
            response = session.get(captcha_url)

            self.last_status_code = response.status_code
            self.last_response_text = response.text

            if response.status_code == 200:
                response_data = response.json()
                return response_data.get('file')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get captcha: {e}")
        return None

    def show_captcha(self, captcha_data, username, captcha_id):
        """Display the captcha image for user input using PIL."""
        try:
            if self.captcha_frame:
                self.captcha_frame.destroy()

            captcha_base64 = captcha_data.split(",")[1] if ',' in captcha_data else captcha_data
            captcha_image_data = base64.b64decode(captcha_base64)

            with open("captcha.jpg", "wb") as f:
                f.write(captcha_image_data)

            captcha_image = cv2.imread("captcha.jpg")
            processed_image = self.process_captcha(captcha_image)

            # Resize the image to 150x80
            processed_image = cv2.resize(processed_image, (150, 80))

            # Convert all black pixels to white
            processed_image[np.all(processed_image == [0, 0, 0], axis=-1)] = [255, 255, 255]

            # Display captcha in tkinter
            image_pil = Image.fromarray(cv2.cvtColor(processed_image, cv2.COLOR_BGR2RGB))
            image_pil.thumbnail((400, 400))

            self.captcha_frame = tk.Frame(self.root)
            self.captcha_frame.pack()

            captcha_image_tk = ImageTk.PhotoImage(image_pil)
            captcha_label = tk.Label(self.captcha_frame, image=captcha_image_tk)
            captcha_label.image = captcha_image_tk
            captcha_label.grid(row=0, column=0, padx=10, pady=10)

            # Create the text entry for OCR output
            ocr_output_entry = tk.Entry(self.captcha_frame, width=40)
            ocr_output_entry.grid(row=0, column=1, padx=10, pady=10)

            # Create the text entry for corrected captcha input
            captcha_entry = tk.Entry(self.captcha_frame)
            captcha_entry.grid(row=1, column=0, padx=10, pady=10)

            submit_button = tk.Button(self.captcha_frame, text="Submit Captcha", command=lambda: threading.Thread(target=self.submit_captcha, args=(username, captcha_id, captcha_entry.get())).start())
            submit_button.grid(row=1, column=1, padx=10, pady=10)

            # Now perform OCR processing
            img_array = np.array(processed_image)
            
            # تحسين الأداء من خلال تحديد أقصى عدد للأحرف المراد التعرف عليها
            predictions = reader.readtext(img_array, detail=0, allowlist='0123456789+-*/')

            # Correct the OCR output with our custom function
            corrected_text, highlighted_image = self.correct_and_highlight(predictions, img_array)

            captcha_solution = self.solve_captcha(corrected_text)

            # Update the OCR output entry with the recognized text
            ocr_output_entry.delete(0, tk.END)  # Clear previous text
            ocr_output_entry.insert(0, corrected_text)  # Insert OCR result

            # Update the entry with OCR result
            captcha_entry.delete(0, tk.END)  # Clear previous text
            captcha_entry.insert(0, captcha_solution)  # Insert solved captcha

            # Bind event to learn from corrected input
            captcha_entry.bind("<Return>", lambda event: self.learn_from_correction(corrected_text, captcha_entry.get()))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to show captcha: {e}")

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
            messagebox.showerror("Error", f"No session found for user {username}")
            return

        # Send OPTIONS request before the GET request
        try:
            options_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha={captcha_solution}"
            session.options(options_url)
        except httpx.RequestError as e:
            messagebox.showerror("Error", f"Failed to send OPTIONS request: {e}")
            return

        # Send GET request to submit the captcha solution
        try:
            get_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha={captcha_solution}"
            response = session.get(get_url)

            if response.status_code == 200:
                response_data = response.json()
                if 'message' in response_data:
                    messagebox.showinfo("Success", response_data['message'])
                else:
                    messagebox.showinfo("Success", "Captcha submitted successfully!")
            else:
                messagebox.showerror("Error", f"Failed to submit captcha. Status code: {response.status_code}, "
                                              f"Response: {response.text}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to submit captcha: {e}")

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
                    self.highlight_element(image, corrected_char, num_color)  # Highlight numbers
                elif corrected_char in "+-*xX×":
                    corrected_text += corrected_char
                    self.highlight_element(image, corrected_char, op_color)  # Highlight operators
                else:
                    corrected_text += corrected_char  # Non-highlighted

        return corrected_text, image

    def highlight_element(self, image, element, color):
        """Highlight elements (numbers/operators) in the image."""
        reader_result = reader.readtext(image)
        for bbox, text, _ in reader_result:
            if element in text:
                # Draw rectangle around the element
                top_left, bottom_right = tuple(map(int, bbox[0])), tuple(map(int, bbox[2]))
                cv2.rectangle(image, top_left, bottom_right, color, 2)

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


if __name__ == "__main__":
    root = tk.Tk()
    app = CaptchaApp(root)
    root.mainloop()
