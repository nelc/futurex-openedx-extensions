"""edx-platform Mocks"""


class CourseMode:  # pylint: disable=too-few-public-methods
    """Mock"""
    @classmethod
    def modes_for_course(
        cls, course_id=None, include_expired=False, only_selectable=True, course=None,
    ):  # pylint: disable=unused-argument
        """Mock"""
        return []
