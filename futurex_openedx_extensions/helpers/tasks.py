"""FX Helpers celery tasks"""
from celery import shared_task
from celery_utils.logged_task import LoggedTask

from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.tasks_utils import export_data_to_csv


@shared_task(base=LoggedTask)
def export_data_to_csv_task(
    fx_task_id: int, url: str, view_data: dict, fx_permission_info: dict, filename: str
) -> None:
    """
    Celery task to mock view with given view params and write JSON response to CSV.
    """
    file = export_data_to_csv(fx_task_id, url, view_data, fx_permission_info, filename)
    if file:
        fx_task = DataExportTask.objects.get(id=fx_task_id)
        fx_task.status = fx_task.STATUS_COMPLETED
        fx_task.save()
