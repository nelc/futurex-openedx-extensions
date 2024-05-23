"""
URLs for dashboard.
"""
from django.conf import settings
from django.urls import re_path

from futurex_openedx_extensions.dashboard import views

app_name = 'fx_dashboard'

urlpatterns = [
    re_path(r'^api/fx/courses/v1/courses/$', views.CoursesView.as_view(), name='courses'),
    re_path(r'^api/fx/learners/v1/learners/$', views.LearnersView.as_view(), name='learners'),
    re_path(
        r'^api/fx/learners/v1/learner/' + settings.USERNAME_PATTERN + '/$',
        views.LearnerInfoView.as_view(),
        name='learner-info'
    ),
    re_path(r'^api/fx/statistics/v1/course_statuses/$', views.CourseStatusesView.as_view(), name='course-statuses'),
    re_path(r'^api/fx/statistics/v1/total_counts/$', views.TotalCountsView.as_view(), name='total-counts'),
]
