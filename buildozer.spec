# (str) Title of your application
title = Captcha Solver

# (str) Package name
package.name = captchasolver

# (str) Package domain (needed for android/ios packaging)
package.domain = org.example

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (list) Application requirements
requirements = python3,kivy,opencv-python,numpy,easyocr,requests,Pillow

# (list) Permissions
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE

# (str) Supported orientation (one of: landscape, portrait, sensor, any)
orientation = portrait

# (str) Application versioning (method 1)
version = 0.1

# (bool) Android: Link against the same version of the Android SDK that your built apk will be built against. Required when you want to compile yourself some custom python libraries
#android.api = 31

# (bool) Can be used to add resource files from any place to your Android APK
android.copy_libs = 1
