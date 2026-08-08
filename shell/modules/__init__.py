"""State sources.  See `shell.modules.base` for the contract.

`build_registry()` wires every module's constructor to the live config so
surfaces can ask for state by name without knowing how it is obtained.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject

from shell.config import Config
from shell.modules.base import Module, ModuleRegistry
from shell.modules.battery import BatteryModule
from shell.modules.brightness import BrightnessModule
from shell.modules.clipboard import ClipboardModule
from shell.modules.clock import ClockModule
from shell.modules.media import MediaModule
from shell.modules.network import BandwidthModule, NetworkModule
from shell.modules.notifications import Notification, NotificationsModule
from shell.modules.timer import TimerModule
from shell.modules.volume import VolumeModule
from shell.modules.wallpaper import WallpaperModule
from shell.modules.weather import WeatherModule
from shell.modules.workspaces import WorkspacesModule

__all__ = [
    "BandwidthModule",
    "BatteryModule",
    "BrightnessModule",
    "ClipboardModule",
    "ClockModule",
    "MediaModule",
    "Module",
    "ModuleRegistry",
    "Notification",
    "NetworkModule",
    "NotificationsModule",
    "TimerModule",
    "VolumeModule",
    "WallpaperModule",
    "WeatherModule",
    "WorkspacesModule",
    "build_registry",
]


def build_registry(config: Config, parent: QObject | None = None) -> ModuleRegistry:
    """Registry with every module's factory bound to `config`."""
    registry = ModuleRegistry(parent)
    registry.register("clock", lambda: ClockModule(config.clock_format))
    registry.register("battery", BatteryModule)
    registry.register("volume", VolumeModule)
    registry.register("brightness", BrightnessModule)
    registry.register("media", MediaModule)
    registry.register("network", NetworkModule)
    registry.register("bandwidth", lambda: BandwidthModule(config.bandwidth_refresh_interval))
    registry.register(
        "notifications",
        lambda: NotificationsModule(config.max_notifications_in_stack, config.avoid_duplicate_notifications),
    )
    registry.register("workspaces", lambda: WorkspacesModule(config.max_workspaces, config.workspace_backend))
    registry.register(
        "weather",
        lambda: WeatherModule(config.weather_location, config.weather_units, config.weather_refresh_interval),
    )
    registry.register("clipboard", ClipboardModule)
    registry.register("wallpaper", lambda: WallpaperModule(config.wallpapers_dir))
    registry.register("timer", lambda: TimerModule(config.timer_presets))
    return registry


def apply_config(registry: ModuleRegistry, config: Config) -> None:
    """Push a reloaded config into whichever modules are currently alive."""
    for module in registry:
        if isinstance(module, ClockModule):
            module.set_format(config.clock_format)
        elif isinstance(module, NotificationsModule):
            module.configure(config.max_notifications_in_stack, config.avoid_duplicate_notifications)
        elif isinstance(module, WorkspacesModule):
            module.set_max(config.max_workspaces)
        elif isinstance(module, WeatherModule):
            module.configure(config.weather_location, config.weather_units, config.weather_refresh_interval)
        elif isinstance(module, WallpaperModule):
            module.set_directory(config.wallpapers_dir)
        elif isinstance(module, TimerModule):
            module.set_presets(config.timer_presets)
        elif isinstance(module, BandwidthModule):
            module.poll_interval_ms = config.bandwidth_refresh_interval
