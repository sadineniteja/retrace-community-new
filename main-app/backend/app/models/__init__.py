"""Database models."""

from app.models.pod import Pod
from app.models.folder_group import FolderGroup, FolderPath
from app.models.product import Product
from app.models.training import TrainingJob
from app.models.query import QueryHistory
from app.models.user import User
from app.models.email_connection import EmailConnection
from app.models.email_inbox import EmailInbox
from app.models.email_message import EmailMessage
from app.models.channel_connection import ChannelConnection

# Brain platform models
from app.models.brain_template import BrainTemplate
from app.models.brain import Brain
from app.models.connected_account import ConnectedAccount
from app.models.brain_schedule import BrainSchedule
from app.models.pipeline_item import PipelineItem
from app.models.brain_task import BrainTask
from app.models.brain_monitor import BrainMonitor
from app.models.brain_activity import BrainActivity
from app.models.approval_request import ApprovalRequest

__all__ = [
    "Pod",
    "FolderGroup",
    "Product",
    "FolderPath",
    "TrainingJob",
    "QueryHistory",
    "User",
    "EmailConnection",
    "EmailInbox",
    "EmailMessage",
    "ChannelConnection",
    # Brain platform
    "BrainTemplate",
    "Brain",
    "ConnectedAccount",
    "BrainSchedule",
    "PipelineItem",
    "BrainTask",
    "BrainMonitor",
    "BrainActivity",
    "ApprovalRequest",
]
