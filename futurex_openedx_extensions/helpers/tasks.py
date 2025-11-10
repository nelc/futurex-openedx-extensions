"""FX Helpers celery tasks"""
import copy
import logging

from celery import shared_task
from celery_utils.logged_task import LoggedTask

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_csv import export_data_to_csv, log_export_task
from futurex_openedx_extensions.helpers.models import DataExportTask

log = logging.getLogger(__name__)


@shared_task(base=LoggedTask)
def export_data_to_csv_task(
    fx_task_id: int, url: str, view_data: dict, fx_permission_info: dict, filename: str
) -> None:
    """
    Celery task to mock view with given view params and write JSON response to CSV.
    """
    try:
        _ = DataExportTask.get_task(fx_task_id)

        if export_data_to_csv(fx_task_id, url, view_data, copy.deepcopy(fx_permission_info), filename):
            DataExportTask.set_status(task_id=fx_task_id, status=DataExportTask.STATUS_COMPLETED)
        else:
            log.info(
                'CSV Export: initiating a continue job starting from page %s for task %s.',
                view_data['start_page'],
                fx_task_id,
            )
            next_view_data = {
                key: view_data[key] for key in [
                    'query_params', 'kwargs', 'path', 'start_page', 'end_page', 'site_domain'
                ]
            }
            async_task = export_data_to_csv_task.delay(fx_task_id, url, next_view_data, fx_permission_info, filename)
            log_export_task(fx_task_id, async_task, continue_job=True)

    except FXCodedException as exc:
        if exc.code == FXExceptionCodes.EXPORT_CSV_TASK_NOT_FOUND.value:
            log.error('CSV Export Error: (%s) %s', exc.code, str(exc))
        else:
            log.error('CSV Export Error for task %s: (%s) %s', fx_task_id, exc.code, str(exc))
            DataExportTask.set_status(task_id=fx_task_id, status=DataExportTask.STATUS_FAILED, error_message=str(exc))
        raise

    except Exception as exc:
        log.error('CSV Export Unhandled Error for task %s: (%s) %s', fx_task_id, exc.__class__.__name__, str(exc))
        DataExportTask.set_status(task_id=fx_task_id, status=DataExportTask.STATUS_FAILED, error_message=str(exc))
        raise
