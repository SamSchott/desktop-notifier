# -*- coding: utf-8 -*-
"""
Notification backend for Linux. Includes an implementation to send desktop notifications
over Dbus. Responding to user interaction with a notification requires a running asyncio
event loop.
"""

# system imports
import sys
import uuid
import logging
from xml.etree.ElementTree import Element, SubElement, tostring
from typing import Optional, TypeVar, cast

# external imports
import winrt.windows.ui.notifications as notifications
import winrt.windows.data.xml.dom as dom

# local imports
from .base import Notification, DesktopNotifierBase, Urgency


__all__ = ["WinRTDesktopNotifier"]

logger = logging.getLogger(__name__)

T = TypeVar("T")


class WinRTDesktopNotifier(DesktopNotifierBase):
    """DBus notification backend for Linux

    This implements the org.freedesktop.Notifications standard. The DBUS connection is
    created in a thread with a running asyncio loop to handle clicked notifications.

    :param app_name: The name of the app. If it matches the application name in an
        existing desktop entry, the icon from that entry will be used by default.
    :param app_icon: The default icon to use for notifications. Will take precedence
        over any icon from the desktop file. Should be a URI or a name in a
        freedesktop.org-compliant icon theme.
    :param notification_limit: Maximum number of notifications to keep in the system's
        notification center.
    """

    _to_native_urgency = {
        Urgency.Low: notifications.ToastNotificationPriority.DEFAULT,
        Urgency.Normal: notifications.ToastNotificationPriority.DEFAULT,
        Urgency.Critical: notifications.ToastNotificationPriority.HIGH,
    }

    def __init__(
        self,
        app_name: str = "Python",
        app_icon: Optional[str] = None,
        notification_limit: Optional[int] = None,
    ) -> None:
        super().__init__(app_name, app_icon, notification_limit)
        self.manager = notifications.ToastNotificationManager.get_default()
        self.notifier = self.manager.create_toast_notifier(sys.executable)

    async def request_authorisation(self) -> bool:
        """
        Request authorisation to send notifications.

        :returns: Whether authorisation has been granted.
        """
        return await self.has_authorisation()

    async def has_authorisation(self) -> bool:
        """
        Whether we have authorisation to send notifications.
        """
        return self.notifier.setting == notifications.NotificationSetting.ENABLED

    async def _send(
        self,
        notification: Notification,
        notification_to_replace: Optional[Notification],
    ) -> str:
        """
        Asynchronously sends a notification via the Dbus interface.

        :param notification: Notification to send.
        :param notification_to_replace: Notification to replace, if any.
        """

        if notification_to_replace:
            platform_nid = cast(str, notification_to_replace.identifier)
        else:
            platform_nid = str(uuid.uuid4())

        # Create notification XML.
        toast_xml = Element("toast", {"launch": "default"})
        visual_xml = SubElement(toast_xml, "visual")
        actions_xml = SubElement(toast_xml, "actions")

        if notification.thread:
            SubElement(
                toast_xml,
                "header",
                {"id": notification.thread, "title": notification.thread},
            )

        binding = SubElement(visual_xml, "binding", {"template": "ToastGeneric"})

        title_xml = SubElement(binding, "text")
        title_xml.text = notification.title

        message_xml = SubElement(binding, "text")
        message_xml.text = notification.message

        if notification.icon:
            SubElement(
                binding,
                "image",
                {"placement": "appLogoOverride", "src": notification.icon},
            )

        if notification.attachment:
            SubElement(
                binding, "image", {"placement": "hero", "src": notification.attachment}
            )

        if notification.reply_field:
            SubElement(actions_xml, "input", {"id": "textBox", "type": "text"})
            SubElement(
                actions_xml,
                "action",
                {
                    "content": notification.reply_field.button_title,
                    "activationType": "background",
                    "arguments": "action=reply",
                },
            )

        for n, button in enumerate(notification.buttons):
            SubElement(
                actions_xml,
                "action",
                {
                    "content": button.title,
                    "activationType": "background",
                    "arguments": f"action={n}",
                },
            )

        if notification.sound:
            SubElement(
                toast_xml, "audio", {"src": "ms-winsoundevent:Notification.Default"}
            )
        else:
            SubElement(toast_xml, "audio", {"silent": "true"})

        xml_document = dom.XmlDocument()
        xml_document.load_xml(tostring(toast_xml, encoding="unicode"))

        native = notifications.ToastNotification(xml_document)
        native.tag = platform_nid
        native.priority = self._to_native_urgency[notification.urgency]

        if notification.thread:
            native.group = notification.thread
        else:
            native.group = "default"

        self.notifier.show(native)

        return platform_nid

    async def _clear(self, notification: Notification) -> None:
        """c
        Asynchronously removes a notification from the notification center
        """
        group = notification.thread or "default"
        self.manager.history.remove(notification.identifier, group, sys.executable)

    async def _clear_all(self) -> None:
        """
        Asynchronously clears all notifications from notification center
        """
        self.manager.history.clear(sys.executable)
