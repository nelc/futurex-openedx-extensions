"""FX Helpers celery tasks"""
from celery import shared_task
from celery_utils.logged_task import LoggedTask

from futurex_openedx_extensions.helpers.export_csv import export_data_to_csv
from futurex_openedx_extensions.helpers.models import DataExportTask


@shared_task(base=LoggedTask)
def export_data_to_csv_task(
    fx_task_id: int, url: str, view_data: dict, fx_permission_info: dict, filename: str
) -> None:
    """
    Celery task to mock view with given view params and write JSON response to CSV.
    """
    export_data_to_csv(fx_task_id, url, view_data, fx_permission_info, filename)
    fx_task = DataExportTask.objects.get(id=fx_task_id)
    fx_task.status = fx_task.STATUS_COMPLETED
    fx_task.save()
