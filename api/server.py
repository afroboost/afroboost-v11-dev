# VERSION 7.0 - PRODUCTION READYCCstasingResponse
class FileResponse:
    def __init__( self, path: Path | str, filename: str | none = None, status_code: int = 200, media_type: str | none = None, headers: dict | none = None, context: Any = None ) -> None:
        self.path = path
        self.filename = filename
        self.status_code = status_code
        self.media_type = media_type or "get_file/application-octet-stream"
        self.headers = headers or {}
        self.context = context
        self.body_iterator = None
        self.initial_message = None
