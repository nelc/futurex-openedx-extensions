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
  * ``api/fx/courses/v1/categories/<category_id>/`` (PATCH) accepted any existing course id in ``courses``; ids are
    now intersected with the caller's courses, and a foreign id is refused like a non-existent one.
  * ``learner/<username>/`` and ``learner_courses/<username>/`` no longer tell a foreign, an unknown, an inactive and
    an ambiguous user apart (404, message ``User not found or not permitted.``, no username echoed); the unenroll
    errors no longer name the user. Error texts changed; status codes are unchanged except an ambiguous email,
    which was 400 and is now the same 404.
  * Before the release, grep the gateway/uwsgi logs for consumers that call learners-by-course (or the v2 accessible
    info) across tenants on purpose: they will now receive empty answers. Not verified here.

* SECURITY (ADR 0009 addendum F2, rule B, no deprecation window): a tenant named in a request body, query or URL
  must be inside the caller's FULL-access reach.

  * ``courses/v1/courses/`` and ``libraries/v1/libraries/`` (POST) accepted any existing ``tenant_id``, so a caller
    with a role in one tenant (even a course-level one) could create courses and libraries in another. A tenant out
    of reach now answers exactly like a non-existent one: 400 with one error on ``tenant_id``.
  * ``courses/v1/course_categories/<course_id>/`` (PUT) refuses (404, like a missing course) a course whose tenant
    the caller reaches only at course level. ``config/v1/draft/<tenant_id>/`` (all methods) answers 403 for a tenant
    the caller reaches only at course level.
  * ``roles/v1/user_roles/`` POST and DELETE refuse the WHOLE request (403) when any tenant in ``tenant_ids`` is out
    of reach; before, POST answered 201 with a per-user failure for such a tenant. System staff is unaffected.

* SECURITY (ADR 0009 addendum F2, rule W, no deprecation window): the ``allow_write`` flag of the roles table
  (``ViewAllowedRoles``) is now enforced. It was stored but never read, so every role listed on a view could use its
  POST/PUT/PATCH/DELETE. A write method now passes only through a role whose row on that view has ``allow_write``;
  reading never needs it; system staff is not subject to it; a role mapped to a user for a view
  (``ViewUserMapping``) stays usable. A caller whose roles may read but not write gets 403
  (``None of the roles of the user allows writing here``).

  * Migration ``0013_backfill_view_allow_write`` sets the flag, before the enforcement matters, on the rows of every
    write-capable view for the roles its declared defaults let write (the declared read-write roles; for
    ``courses_list`` and ``libraries_list``, which declare none, the roles they list today). It only ever turns
    False into True, so it is safe to run twice, and it leaves untouched any row an operator created or edited
    (a row with a history record), logging those at WARNING so they can be reviewed.
  * Seeding of a view's rows now sets ``allow_write`` from the view's default WRITE roles; it used the read-only list,
    which marked every seeded role writable, including on views that cannot write.
  * Operators: before deploying, diff the roles table against the defaults and check 30 days of write calls per view
    and role (see the US-9 ticket). A writer whose row says ``allow_write=False`` will receive 403 after the upgrade.

0.1.0 – 2024-03-05
**********************************************

Added
=====

* First release on PyPI.
