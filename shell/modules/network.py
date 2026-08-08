"""Network state: WiFi connection, available networks, and bandwidth counters.

Two modules because they change on completely different timescales -- the
connection flips rarely and matters to the pill bar icon, while the byte
counters are read on a long interval for the dashboard readout.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from shell.modules.base import Module
from shell.platform import IS_WINDOWS
from shell.platform.system import local_ip

logger = logging.getLogger(__name__)

# MIB_IF_ROW2 / IF_TYPE constants
IF_OPER_STATUS_UP = 1
IF_TYPE_SOFTWARE_LOOPBACK = 24
IF_TYPE_TUNNEL = 131
#: GetIfEntry2 wants a real interface index; Windows keeps them small and
#: sparse, so a bounded scan is both simpler and faster than enumerating
#: adapters through GetAdaptersAddresses just to get the same indices.
MAX_INTERFACE_INDEX = 64


class NetworkModule(Module):
    """Connectivity: interface type, SSID, signal strength, local IP."""

    name = "network"
    poll_interval_ms = 5000

    def refresh(self) -> None:
        # Both the route lookup and the WLAN call are quick, but "quick" on the
        # GUI thread is still a stutter in the pill's animation, so they go wide.
        self.run_async(self._probe, lambda result: self.update(**result))

    def _probe(self) -> dict[str, Any]:
        ip = local_ip()
        connected = ip != "0.0.0.0"
        wifi = self._wifi_status()
        return {
            "connected": connected,
            "ip": ip,
            "kind": "wifi" if wifi else ("ethernet" if connected else "none"),
            "ssid": wifi.get("ssid", "") if wifi else "",
            "signal": wifi.get("signal", 0) if wifi else 0,
        }

    def _wifi_status(self) -> dict[str, Any] | None:
        """Current WLAN connection, or None when not on WiFi."""
        networks = self.available_networks()
        for network in networks:
            if network["connected"]:
                return network
        return None

    def available_networks(self) -> list[dict[str, Any]]:
        """Every SSID the adapter can currently see, strongest first.

        Read straight out of `WlanGetAvailableNetworkList`, which also carries
        the CONNECTED flag -- so one call answers both "what am I on" and "what
        else is there" without a separate connection query.
        """
        if not IS_WINDOWS:
            return []
        try:
            import ctypes
            from ctypes import POINTER, byref, cast, wintypes

            from vendor.win32.bindings.wlanapi import (
                WlanCloseHandle,
                WlanEnumInterfaces,
                WlanFreeMemory,
                WlanGetAvailableNetworkList,
                WlanOpenHandle,
            )
            from vendor.win32.constants import (
                ERROR_SUCCESS,
                WLAN_AVAILABLE_NETWORK_CONNECTED,
                WLAN_AVAILABLE_NETWORK_HAS_PROFILE,
            )
            from vendor.win32.structs import (
                WLAN_AVAILABLE_NETWORK,
                WLAN_AVAILABLE_NETWORK_LIST,
                WLAN_INTERFACE_INFO_LIST,
            )
        except Exception as exc:
            logger.debug("wlanapi unavailable: %s", exc)
            return []

        handle = wintypes.HANDLE()
        negotiated = wintypes.DWORD()
        try:
            if WlanOpenHandle(2, None, byref(negotiated), byref(handle)) != ERROR_SUCCESS:
                return []
        except OSError as exc:  # no WLAN service on desktops without a radio
            logger.debug("WlanOpenHandle failed: %s", exc)
            return []

        results: list[dict[str, Any]] = []
        interface_list = POINTER(WLAN_INTERFACE_INFO_LIST)()
        try:
            if WlanEnumInterfaces(handle, None, byref(interface_list)) != ERROR_SUCCESS:
                return []
            count = interface_list.contents.dwNumberOfItems
            for index in range(count):
                guid = interface_list.contents.InterfaceInfo[index].InterfaceGuid
                network_list = POINTER(WLAN_AVAILABLE_NETWORK_LIST)()
                if WlanGetAvailableNetworkList(handle, byref(guid), 0, None, byref(network_list)) != ERROR_SUCCESS:
                    continue
                try:
                    total = network_list.contents.dwNumberOfItems
                    # `Network` is a flexible array declared as [1]; re-cast it
                    # to its real length before walking it.
                    array = cast(
                        ctypes.addressof(network_list.contents.Network),
                        POINTER(WLAN_AVAILABLE_NETWORK * total),
                    ).contents
                    for entry in array:
                        ssid = str(entry.dot11Ssid)
                        if not ssid:
                            continue  # hidden network; nothing useful to show
                        results.append(
                            {
                                "ssid": ssid,
                                "signal": int(entry.wlanSignalQuality),
                                "secure": bool(entry.bSecurityEnabled),
                                "known": bool(entry.dwFlags & WLAN_AVAILABLE_NETWORK_HAS_PROFILE),
                                "connected": bool(entry.dwFlags & WLAN_AVAILABLE_NETWORK_CONNECTED),
                            }
                        )
                finally:
                    WlanFreeMemory(network_list)
        except Exception as exc:
            logger.debug("WLAN enumeration failed: %s", exc)
        finally:
            if interface_list:
                with suppress(Exception):
                    WlanFreeMemory(interface_list)
            with suppress(Exception):
                WlanCloseHandle(handle, None)

        # Duplicate SSIDs appear once per BSSID; keep the strongest of each.
        best: dict[str, dict[str, Any]] = {}
        for network in results:
            existing = best.get(network["ssid"])
            if existing is None or network["signal"] > existing["signal"]:
                best[network["ssid"]] = network
        return sorted(best.values(), key=lambda n: (-n["connected"], -n["signal"]))

    @staticmethod
    def open_network_flyout() -> bool:
        """Hand joining a network to Windows.

        Creating and applying WLAN profiles is a 1,400-line problem in yasb and
        duplicates a flyout every Windows machine already has, so ChillPill
        shows the network list and delegates the actual join.
        """
        from shell.platform.system import open_path

        return open_path("ms-availablenetworks:")


class BandwidthModule(Module):
    """Cumulative and per-interval byte counters from GetIfEntry2.

    The default interval is five minutes because the original shell shows a
    session total, not a live speedometer -- polling every second would be a
    different (and much noisier) feature.
    """

    name = "bandwidth"
    poll_interval_ms = 300_000

    def __init__(self, interval_ms: int = 300_000, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.poll_interval_ms = interval_ms
        self._previous: tuple[int, int] | None = None

    def refresh(self) -> None:
        self.run_async(self._read_counters, self._apply)

    def _apply(self, totals: tuple[int, int] | None) -> None:
        if totals is None:
            return
        received, sent = totals
        if self._previous is not None:
            previous_received, previous_sent = self._previous
            # Counters reset when an adapter disappears; treat a drop as a reset.
            delta_received = max(0, received - previous_received)
            delta_sent = max(0, sent - previous_sent)
            seconds = max(1.0, self.poll_interval_ms / 1000.0)
            self.update(
                down_rate=delta_received / seconds,
                up_rate=delta_sent / seconds,
                down_delta=delta_received,
                up_delta=delta_sent,
            )
        self._previous = totals
        self.update(down_total=received, up_total=sent)

    def _read_counters(self) -> tuple[int, int] | None:
        if not IS_WINDOWS:
            return None
        try:
            import ctypes

            from vendor.win32.bindings.iphlpapi import iphlpapi
            from vendor.win32.structs import MIB_IF_ROW2
        except Exception as exc:
            logger.debug("iphlpapi unavailable: %s", exc)
            return None

        received = sent = 0
        for index in range(1, MAX_INTERFACE_INDEX + 1):
            row = MIB_IF_ROW2()
            row.InterfaceIndex = index
            if iphlpapi.GetIfEntry2(ctypes.byref(row)) != 0:
                continue
            if row.OperStatus != IF_OPER_STATUS_UP:
                continue
            if row.Type in (IF_TYPE_SOFTWARE_LOOPBACK, IF_TYPE_TUNNEL):
                continue
            received += int(row.InOctets)
            sent += int(row.OutOctets)
        return received, sent


def format_bytes(value: float) -> str:
    """1536 -> '1.5 KB'."""
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_rate(bytes_per_second: float) -> str:
    return f"{format_bytes(bytes_per_second)}/s"
