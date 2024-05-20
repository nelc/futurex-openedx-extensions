"""edx-platform models mocks for testing purposes."""
from django.contrib.auth import get_user_model
from django.db import models
from opaque_keys.edx.django.models import CourseKeyField


class CourseOverview(models.Model):
    """Mock"""
    id = models.CharField(max_length=255, primary_key=True)  # pylint: disable=invalid-name
    org = models.CharField(max_length=255)
    catalog_visibility = models.TextField(null=True)
    start = models.DateTimeField(null=True)
    end = models.DateTimeField(null=True)
    display_name = models.TextField(null=True)
    enrollment_start = models.DateTimeField(null=True)
    enrollment_end = models.DateTimeField(null=True)
    self_paced = models.BooleanField(default=False)
    course_image_url = models.TextField()
    visible_to_staff_only = models.BooleanField(default=False)

    class Meta:
        app_label = "fake_models"
        db_table = "course_overviews_courseoverview"


class CourseAccessRole(models.Model):
    """Mock"""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    role = models.CharField(max_length=255)
    org = models.CharField(blank=True, max_length=255)

    class Meta:
        app_label = "fake_models"
        db_table = "student_courseaccessrole"


class CourseEnrollment(models.Model):
    """Mock"""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    course = models.ForeignKey(CourseOverview, on_delete=models.CASCADE)
    is_active = models.BooleanField()

    class Meta:
        app_label = "fake_models"
        db_table = "student_courseenrollment"


class UserSignupSource(models.Model):
    """Mock"""
    site = models.CharField(max_length=255)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    class Meta:
        app_label = "fake_models"
        db_table = "student_usersignupsource"


class GeneratedCertificate(models.Model):
    """Mock"""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    course_id = CourseKeyField(max_length=255, blank=True, default=None)
    status = models.CharField(max_length=32, default='unavailable')

    class Meta:
        unique_together = (('user', 'course_id'),)
        app_label = "fake_models"
        db_table = "certificates_generatedcertificate"


class UserProfile(models.Model):
    """Mock"""
    user = models.OneToOneField(
        get_user_model(), unique=True, db_index=True, related_name='profile', on_delete=models.CASCADE
    )
    name = models.CharField(blank=True, max_length=255, db_index=True)
    year_of_birth = models.IntegerField(blank=True, null=True, db_index=True)
    GENDER_CHOICES = (
        ('m', 'Male'),
        ('f', 'Female'),
    )
    gender = models.CharField(
        blank=True, null=True, max_length=6, db_index=True, choices=GENDER_CHOICES
    )
    profile_image_uploaded_at = models.DateTimeField(null=True, blank=True)
    phone_number = models.CharField(blank=True, null=True, max_length=50)

    @property
    def has_profile_image(self):
        """
        Convenience method that returns a boolean indicating whether or not
        this user has uploaded a profile image.
        """
        return self.profile_image_uploaded_at is not None

    class Meta:
        app_label = "fake_models"
        db_table = "auth_userprofile"


class BaseFeedback(models.Model):
    """Mock"""
    RATING_OPTIONS = [
        (0, '0'),
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5')
    ]
    author = models.ForeignKey(get_user_model(), null=True, on_delete=models.SET_NULL)
    rating_content = models.IntegerField(blank=True, null=True, choices=RATING_OPTIONS)
    feedback = models.CharField(max_length=500, blank=True, null=True)
    public = models.BooleanField(null=True, default=False)
    course_id = models.ForeignKey(CourseOverview, null=True, on_delete=models.SET_NULL)

    class Meta:
        """Set model abstract"""
        abstract = True


class FeedbackCourse(BaseFeedback):
    """Mock"""
    rating_instructors = models.IntegerField(blank=True, null=True, choices=BaseFeedback.RATING_OPTIONS)
    recommended = models.BooleanField(null=True, default=True)

    class Meta:
        """Set constrain for author an course id"""
        unique_together = [["author", "course_id"]]
        db_table = "eox_nelp_feedbackcourse"
