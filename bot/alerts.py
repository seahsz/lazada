"""Get your attention: console banner, beeps, and optional phone push via ntfy.sh."""
import logging
import threading
import urllib.request

log = logging.getLogger(__name__)

try:
    import winsound
except ImportError:  # not on Windows
    winsound = None


class Alerter:
    def __init__(self, sound: bool = True, ntfy_topic: str | None = None):
        self.sound = sound
        self.ntfy_topic = ntfy_topic

    def alert(self, title: str, message: str, urgent: bool = False) -> None:
        print("\n" + "!" * 60)
        print(f"  {title}")
        print(f"  {message}")
        print("!" * 60 + "\n")
        log.warning("%s - %s", title, message)
        if self.sound:
            threading.Thread(target=self._beep, args=(6 if urgent else 2,), daemon=True).start()
        if self.ntfy_topic:
            threading.Thread(target=self._push, args=(title, message, urgent), daemon=True).start()

    def _beep(self, times: int) -> None:
        for _ in range(times):
            if winsound:
                winsound.Beep(1500, 300)
                winsound.Beep(1000, 300)
            else:
                print("\a", end="", flush=True)

    def _push(self, title: str, message: str, urgent: bool) -> None:
        req = urllib.request.Request(
            f"https://ntfy.sh/{self.ntfy_topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "urgent" if urgent else "default"},
        )
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as e:
            log.warning("ntfy push failed: %s", e)
