import os.path
import mimetypes

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']  # Upload-only access

def upload_to_drive(filepath):
    creds = None

    # Load existing token
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # No token or expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This will open a browser window
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Build the Drive API client
    service = build('drive', 'v3', credentials=creds)

    # File metadata and MIME type
    filename = os.path.basename(filepath)
    mime_type, _ = mimetypes.guess_type(filepath)
    mime_type = mime_type or 'application/octet-stream'

    file_metadata = {'name': filename}
    media = MediaFileUpload(filepath, mimetype=mime_type)

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    print(f"Uploaded successfully!")
    print(f"File ID: {file.get('id')}")
    print(f"View link: {file.get('webViewLink')}")

# ✅ Usage:
upload_to_drive('data/20250717_152741.csv')
