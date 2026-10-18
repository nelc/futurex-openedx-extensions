Change Log
##########

..
   All enhancements and patches to futurex_openedx_extensions will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
**********

* Added the read-only pending course invitations endpoint (``api/fx/learners/v1/pending_invitations/``), with an
  access log for every view and export. The learners list is unchanged. Version 0.14.0.
* Added the bulk course progress feed: ``api/fx/learners/v1/learner_courses/`` without a username returns one row per
  active enrollment with course completion above zero (national_id, user_id, email, course_id, date_joined,
  last_login, course_score, progress, certificate_available, certificate_date, grade, passed). Each request reads one
  window of 20,000 enrollment ids (up to ``page_size`` rows, 1000 by default and at most), so pages can be short or
  empty: follow ``next`` until it is null. No total count, optional ``modified_since`` filter. All values come from
  stored data in one query per page. The per-learner route with a username is unchanged.
* SECURITY (ADR 0009, no deprecation window): a course or user named in the URL, query or body is now checked
  against the caller's reach before anything is read or changed.

  * ``api/fx/learners/v1/learners/<course-id>/`` (and its CSV export) served the learners of ANY course to any caller
    holding a role in some tenant. A course outside the caller's scope now answers an empty list, identical to a
    non-existent course.
  * ``api/fx/roles/v1/user_roles/<username>/`` (PUT) accepted a ``tenant_id`` in the body without checking the
    caller's reach, so it could change another tenant's roles of a user. It now answers 403 for a tenant the caller
    does not fully reach.
  * ``api/fx/accessible/v2/info/`` returned the tenants of any user named in ``username_or_email``. It now returns
    only tenants the caller reaches itself (an unknown user and a user with none in common both answer ``{}``).
  * ``learner/<username>/`` and ``learner_courses/<username>/`` no longer tell a foreign, an unknown, an inactive and
    an ambiguous user apart (404, message ``User not found or not permitted.``, no username echoed); the unenroll
    errors no longer name the user. Error texts changed; status codes are unchanged except an ambiguous email,
    which was 400 and is now the same 404.
  * Before the release, grep the gateway/uwsgi logs for consumers that call learners-by-course (or the v2 accessible
    info) across tenants on purpose: they will now receive empty answers. Not verified here.

0.1.0 – 2024-03-05
**********************************************

Added
=====

* First release on PyPI.
