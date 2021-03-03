# -*- coding: utf-8 -*-
"""
Notification backend for Linux. Includes an implementation to send desktop notifications
over Dbus. Responding to user interaction with a notification requires a running asyncio
event loop.
"""

# system imports
import uuid
import logging
from xml.etree.ElementTree import Element, SubElement, tostring
from typing import Optional, TypeVar, cast

# external imports
from winrt.windows.ui.notifications import (
    ToastNotificationManager,
    ToastNotificationPriority,
    NotificationSetting,
    ToastNotification,
    ToastActivatedEventArgs,
    ToastDismissalReason,
)
from winrt.windows.data.xml import dom
from winrt.windows.applicationmodel.core import CoreApplication
from winrt.windows.applicationmodel.background import (
    BackgroundTaskRegistration,
    BackgroundTaskBuilder,
    BackgroundExecutionManager,
    ToastNotificationActionTrigger,
)

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
        Urgency.Low: ToastNotificationPriority.DEFAULT,
        Urgency.Normal: ToastNotificationPriority.DEFAULT,
        Urgency.Critical: ToastNotificationPriority.HIGH,
    }

    background_task_name = "DesktopNotifier-ToastBackgroundTask"

    def __init__(
        self,
        app_name: str = "Python",
        app_icon: Optional[str] = None,
        notification_limit: Optional[int] = None,
    ) -> None:
        super().__init__(app_name, app_icon, notification_limit)
        self._appid = CoreApplication.get_id()
        self.manager = ToastNotificationManager.get_default()
        self.notifier = self.manager.create_toast_notifier(self._appid)

        # BackgroundExecutionManager.remove_access(self._appid)
        # CoreApplication.add_background_activated(self._on_background_activated)

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
        return self.notifier.setting == NotificationSetting.ENABLED

    async def _request_background_task_access(self) -> None:
        """Request permission to activate in the background."""

        # If background task is already registered, do nothing.
        tasks = BackgroundTaskRegistration.get_all_tasks()
        if any(t.value.name == self.background_task_name for t in tasks):
            return

        # Otherwise request access.
        await BackgroundExecutionManager.request_access_async(self._appid)

        # Create the background tasks.
        builder = BackgroundTaskBuilder()
        builder.name = self.background_task_name

        builder.set_trigger(ToastNotificationActionTrigger())
        builder.register()

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

        await self._request_background_task_access()

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
                    "arguments": "action=reply&amp",
                    "hint-inputId": "textBox",
                },
            )

        for n, button in enumerate(notification.buttons):
            SubElement(
                actions_xml,
                "action",
                {
                    "content": button.title,
                    "activationType": "background",
                    "arguments": str(n),
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

        native = ToastNotification(xml_document)
        native.tag = platform_nid
        native.priority = self._to_native_urgency[notification.urgency]

        if notification.thread:
            native.group = notification.thread
        else:
            native.group = "default"

        def on_activated(sender, activated_args):
            activated_args = ToastActivatedEventArgs._from(activated_args)
            action_id = activated_args.arguments

            if action_id == "default":
                if notification.on_clicked:
                    notification.on_clicked()

            elif action_id == "action=reply&amp":
                if notification.reply_field.on_replied:
                    notification.reply_field.on_replied(activated_args.user_input)

            else:
                action_number = int(action_id)
                notification.buttons[action_number].on_pressed()

        def on_dismissed(sender, dismissed_args):

            self._clear_notification_from_cache(notification)

            if dismissed_args.reason == ToastDismissalReason.USER_CANCELED:
                if notification.on_dismissed:
                    notification.on_dismissed()

        def on_failed(sender, failed_args):
            logger.warning(
                f"Notification failed (error code {failed_args.error_code.value})"
            )

        native.add_activated(on_activated)
        native.add_dismissed(on_dismissed)
        native.add_failed(on_failed)

        self.notifier.show(native)

        return platform_nid

    async def _clear(self, notification: Notification) -> None:
        """c
        Asynchronously removes a notification from the notification center
        """
        group = notification.thread or "default"
        self.manager.history.remove(notification.identifier, group, self._appid)

    async def _clear_all(self) -> None:
        """
        Asynchronously clears all notifications from notification center
        """
        self.manager.history.clear(self._appid)
