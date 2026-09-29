import os
import threading
import mimetypes

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

DRIVE_CONFIG = {
    "credentials_path": os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        os.path.join(RESOURCE_DIR, "credentials.json"),
    ),
    "token_path": os.getenv(
        "GOOGLE_TOKEN_PATH",
        os.path.join(RESOURCE_DIR, "token.json"),
    ),
    "folder_name": "VitalX_data",
    "scopes": ["https://www.googleapis.com/auth/drive.file"]
}

class DriveUploader(threading.Thread):
    def __init__(self, folder_name = DRIVE_CONFIG["folder_name"],
                 credentials_path = DRIVE_CONFIG["credentials_path"],
                 token_path = DRIVE_CONFIG["token_path"],
                 scopes = DRIVE_CONFIG["scopes"]):
        super().__init__()
        self.creds = None
        self.service = None
        self.folder_name = folder_name
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.scopes = scopes
        self.folder_id = None
        self.view_link = None  # Store the file's webViewLink

    def authenticate(self):
        if os.path.exists(self.token_path):
            self.creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.scopes)
                self.creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(os.path.abspath(self.token_path)), exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
        self.service = build('drive', 'v3', credentials=self.creds)

    def get_or_create_folder(self):
        query = f"name = '{self.folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = self.service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        folders = results.get('files', [])
        if folders:
            self.folder_id = folders[0]['id']
        else:
            file_metadata = {
                'name': self.folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(body=file_metadata, fields='id').execute()
            self.folder_id = folder.get('id')

    def make_file_public(self, file_id):
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        self.service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()

    def upload_file(self, filepath):
        filename = os.path.basename(filepath)
        mime_type, _ = mimetypes.guess_type(filepath)
        mime_type = mime_type or 'application/octet-stream'

        file_metadata = {
            'name': filename,
            'parents': [self.folder_id]
        }
        media = MediaFileUpload(filepath, mimetype=mime_type)

        uploaded_file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        # Make file public
        self.make_file_public(uploaded_file['id'])

        self.view_link = uploaded_file.get('webViewLink')

        print(f"[DriveUploader] File uploaded successfully!")
        print(f"[DriveUploader] Public View Link: {self.view_link}")

        return self.view_link
