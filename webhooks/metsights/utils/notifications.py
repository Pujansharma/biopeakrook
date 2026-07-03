import threading

from webhooks.metsights.utils.reports import perform_file_upload_action


class NotificationThread(threading.Thread):
    def __init__(self, data: dict):
        self.data = data
        threading.Thread.__init__(self)

    def run(self) -> None:
        perform_file_upload_action(self.data)


def send_metsights_file_upload_notification(data: dict) -> None:
    NotificationThread(data).start()
