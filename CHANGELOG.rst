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

* SECURITY (ADR 0009 addendum F2, rules R and A, no deprecation window): ``roles/v1/user_roles/`` authority.

  * PUT (update) checked the authority to DROP a role against the wrong data shape, so the check never fired: a
    caller holding any role allowed to write on the view (for example an org-wide instructor) could erase ALL the
    roles of a tenant admin in the tenant (the request answered 400 for the refused grant, but the deletion had
    already been committed). Dropping a role by update now needs the same authority as deleting it, and a failed update
    is rolled back as a whole.
  * Nobody can grant or change their own roles through the API (400, code 2007 on PUT; a failed entry, code 2002, in
    the POST result). System staff is exempt.
  * PUT and DELETE answer the same 404 (``User not found or not permitted.``) for an unknown username, an ambiguous
    email, and a user who never signed up on, and holds no role in, a tenant the caller fully reaches. The messages
    of the lookup (``... does not exist!``, ``Multiple users found ...``) are gone.
  * POST (N1): a failed entry for a key that is unknown, inactive, ambiguous, or an existing user outside the
    caller's reach (never signed up on, and holding no role in, a tenant the caller fully reaches) is now ONE shape:
    ``reason_code`` USER_NOT_FOUND, message ``User with <ID|username/email> (<key as sent>) does not exist!``,
    and only the key as the caller sent it (a numeric id no longer returns the real username and email). Users the
    caller can see keep the detailed reason. Onboarding is unchanged: a user holding roles only in another tenant
    still receives the role (``added``/``updated``); that success is the one remaining difference from an unknown key.

* SECURITY (ADR 0009 addendum F2, no deprecation window): ``redirect/set_theme_preview/`` (unauthenticated) followed
  any ``next`` value: an open redirect, and the value was written into a JavaScript string with HTML escaping only.
  ``next`` is now accepted only as a path of this site (one leading ``/``) or an absolute URL on the request host or
  one of the platform's tenant hosts; anything else (``//host``, backslash forms, ``javascript:``, other hosts,
  control characters, an empty value) answers 400, before both the redirect and the interstitial page, and the value
  is JavaScript-escaped in the page.

* ``api/fx/accessible/v1/info/`` (anonymous by design, used by the login flow) keeps its response unchanged (ADR 0009
  addendum F2, option A) but anonymous callers are now rate-limited per client address (429 when exceeded; setting
  ``FX_ANONYMOUS_LOOKUP_THROTTLE_RATE``, default ``60/minute``) and every lookup is logged (logger
  ``futurex_openedx_extensions.accessible_info_access``: client address, a short KEYED hash (HMAC-SHA256) of the
  looked-up value, and the tenant count, never the username or email; refusals on
  ``futurex_openedx_extensions.anonymous_lookup``). Which tenants a given email belongs to is still readable by
  anyone who stays under the limit: narrowing the answer needs the login owner to name the fields it reads. Behind proxies DRF's ``NUM_PROXIES`` must be set for the client
  address to be the real one.

  * REQUIRED NEW SETTING (N2): ``FX_ANONYMOUS_LOOKUP_LOG_SALT``, the secret of that hash. There is NO default. Set it
    as a committed literal per environment in nassau (``stage_config`` / ``prod_config``), exactly like
    ``EOX_NELP_ENROLLMENT_LOG_SALT`` (decision a6-salt-source), BEFORE or with the image that carries this version
    (the setting is ignored by older versions). While it is unset or empty, ``accessible/v1/info`` raises
    ``ImproperlyConfigured`` (HTTP 500, nothing looked up, nothing logged): the login lookup fails until it is set.

0.1.0 – 2024-03-05
**********************************************

Added
=====

* First release on PyPI.
