import os
import time
import logging
import threading
from typing import Any

from swchp2pcom import SwchPeer


class P2PAgent:
    def __init__(self):
        self.peer_id = os.getenv("PEER_ID", "unknown-service")
        self.hub_host = os.getenv("P2P_HUB_HOST", "customdas-p2p-hub")
        self.hub_port = int(os.getenv("P2P_HUB_PORT", "5000"))
        self.is_hub = os.getenv("IS_P2P_HUB", "false").lower() == "true"

        self.startup_delay = float(os.getenv("P2P_STARTUP_DELAY_SECONDS", "0"))
        self.retry_seconds = float(os.getenv("P2P_RETRY_SECONDS", "5"))

        self.peer: SwchPeer | None = None
        self.ready = False

        # Thread-safe storage for cross-thread messaging delivery to das_loop
        self._inbox_lock = threading.Lock()
        self._message_inbox: list[dict[str, Any]] = []

    def handle_hello(self, peer_id: str, message: dict[str, Any]):
        logging.info("Received HELLO from %s: %s", peer_id, message)

    def handle_bottleneck_alert(self, peer_id: str, message: dict[str, Any]):
        """
        Reactive callback triggered by swchp2pcom network engine thread 
        whenever an upstream service screams backpressure alerts down the topology tree.
        """
        logging.info("[P2P EVENT] Received BOTTLENECK ALERT from upstream parent %s: %s", peer_id, message)
        
        alert_payload = {
            "type": "MSG_BOTTLENECK_ALERT",
            "from": peer_id,
            "timestamp": message.get("timestamp", time.time()),
            "data": message
        }
        
        with self._inbox_lock:
            self._message_inbox.append(alert_payload)

    def get_messages(self) -> list[dict[str, Any]]:
        """
        Drains and harvests all accumulated incoming messages since the last polling loop interval.
        Thread-safe for das_loop invocation.
        """
        with self._inbox_lock:
            messages = list(self._message_inbox)
            self._message_inbox.clear()
        return messages

    def init_peer(self):
        metadata = {
            "peer_type": "AUTOSCALE_AGENT",
            "service": self.peer_id,
            "is_hub": self.is_hub,
        }

        if self.is_hub:
            self.peer = SwchPeer(
                peer_id=self.peer_id,
                listen_ip="0.0.0.0",
                listen_port=self.hub_port,
                public_ip=self.hub_host,
                public_port=self.hub_port,
                metadata=metadata,
            )
            logging.info(
                "Initialised HUB peer %s listening on 0.0.0.0:%s public=%s:%s",
                self.peer_id,
                self.hub_port,
                self.hub_host,
                self.hub_port,
            )

        else:
            self.peer = SwchPeer(
                peer_id=self.peer_id,
                enable_rejoin=True,
                metadata=metadata,
            )
            logging.info("Initialised WORKER peer %s", self.peer_id)

        # Wire up message event targets
        self.peer.register_message_handler("MSG_HELLO", self.handle_hello)
        self.peer.register_message_handler("MSG_BOTTLENECK_ALERT", self.handle_bottleneck_alert)

    def start(self):
        """
        Blocking call.

        Run this in the main thread.
        Run the DAS/autoscaler loop in a background thread.
        """
        if self.peer is None:
            raise RuntimeError("Peer not initialised. Call init_peer() first.")

        if self.startup_delay > 0:
            logging.info("P2P startup delay %.1fs for %s", self.startup_delay, self.peer_id)
            time.sleep(self.startup_delay)

        if self.is_hub:
            self.ready = True
            logging.info("Starting as P2P HUB: %s", self.peer_id)
            self.peer.start()
            return

        self._try_enter_hub()
        self.peer.start()

    def _try_enter_hub(self):
        if self.peer is None:
            return

        logging.info(
            "Trying to enter P2P hub %s:%s as %s",
            self.hub_host,
            self.hub_port,
            self.peer_id,
        )

        def on_entered(_=None):
            self.ready = True
            logging.info(
                "Connected to P2P hub %s:%s as %s",
                self.hub_host,
                self.hub_port,
                self.peer_id,
            )

        def on_failed(err):
            self.ready = False
            logging.warning(
                "Failed to enter P2P hub as %s, retrying in %.1fs: %s",
                self.peer_id,
                self.retry_seconds,
                err,
            )

            try:
                from twisted.internet import reactor
                reactor.callLater(self.retry_seconds, self._try_enter_hub)
            except Exception as exc:
                logging.warning("Could not schedule P2P retry: %s", exc)

        d = self.peer.enter(self.hub_host, self.hub_port)
        d.addCallback(on_entered)
        d.addErrback(on_failed)

    def send_message(self, target: str, msg_type: str, payload: dict[str, Any]) -> bool:
        if self.peer is None:
            logging.warning("P2P peer not initialised")
            return False

        if not self.ready:
            logging.info("P2P not ready, skip send to %s", target)
            return False

        if target in ("", "unknown", None):
            logging.info("Invalid target peer, skip: %s", target)
            return False

        try:
            logging.info("Sending %s to %s: %s", msg_type, target, payload)
            self.peer.send(target, msg_type, payload)
            return True

        except ValueError as exc:
            logging.info("Peer %s not available in registry yet: %s", target, exc)
            return False

        except Exception as exc:
            logging.exception("Unexpected P2P send error to %s: %s", target, exc)
            return False

    def get_known_peers(self) -> set[str]:
        if self.peer is None or not self.ready:
            return set()

        try:
            peers = self.peer.find_peers({"peer_type": "AUTOSCALE_AGENT"})
            return set(peers)
        except Exception as exc:
            logging.warning("Could not discover peers: %s", exc)
            return set()

    def broadcast_hello(self):
        known_peers = self.get_known_peers()

        for peer_id in known_peers:
            if peer_id == self.peer_id:
                continue

            self.send_message(
                peer_id,
                "MSG_HELLO",
                {
                    "from": self.peer_id,
                    "msg": "hello",
                    "timestamp": time.time(),
                },
            )