from .common import *

@admin_required
def admin_announcements(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            announcement = get_object_or_404(Announcement, pk=request.POST.get("announcement_id"))
            title = announcement.title
            announcement.delete()
            messages.success(request, f"'{title}' 공지를 삭제했습니다.")
            return _redirect_back(request, "admin_announcements")

        if action == "toggle":
            announcement = get_object_or_404(Announcement, pk=request.POST.get("announcement_id"))
            announcement.is_published = not announcement.is_published
            announcement.save(update_fields=["is_published", "updated_at"])
            messages.success(request, "공지 공개 상태를 변경했습니다.")
            return _redirect_back(request, "admin_announcements")

        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        priority = request.POST.get("priority", Announcement.Priority.NORMAL)
        publish_at = _parse_optional_datetime(request.POST.get("publish_at")) or timezone.now()
        expires_at = _parse_optional_datetime(request.POST.get("expires_at"))
        is_published = request.POST.get("is_published") == "1"
        if not title or not body:
            messages.error(request, "공지 제목과 내용을 모두 입력해주세요.")
            return _redirect_back(request, "admin_announcements")
        if priority not in Announcement.Priority.values:
            priority = Announcement.Priority.NORMAL
        if expires_at and expires_at <= publish_at:
            messages.error(request, "종료 시각은 공개 시각보다 늦어야 합니다.")
            return _redirect_back(request, "admin_announcements")

        if action == "update":
            announcement = get_object_or_404(Announcement, pk=request.POST.get("announcement_id"))
            announcement.title = title
            announcement.body = body
            announcement.priority = priority
            announcement.publish_at = publish_at
            announcement.expires_at = expires_at
            announcement.is_published = is_published
            announcement.save()
            messages.success(request, "공지를 수정했습니다.")
        else:
            Announcement.objects.create(
                title=title, body=body, priority=priority, publish_at=publish_at,
                expires_at=expires_at, is_published=is_published, created_by=request.user,
            )
            messages.success(request, "새 공지를 등록했습니다.")
        return _redirect_back(request, "admin_announcements")

    announcements = list(Announcement.objects.select_related("created_by").filter(target_all=True)[:100])
    now = timezone.now()
    active_students = list(Student.objects.filter(is_active=True).select_related("user").order_by("user__first_name", "user__username"))
    active_student_ids = {student.id for student in active_students}
    student_count = len(active_students)
    total_reads = 0

    for item in announcements:
        read_student_ids = set(
            item.reads.filter(student_id__in=active_student_ids).values_list("student_id", flat=True)
        )
        item.read_count = len(read_student_ids)
        item.target_count = student_count
        item.unread_count = max(student_count - item.read_count, 0)
        item.read_rate = round((item.read_count / student_count) * 100) if student_count else 0
        item.read_students = [student for student in active_students if student.id in read_student_ids]
        item.unread_students = [student for student in active_students if student.id not in read_student_ids]
        item.is_live = item.is_published and item.publish_at <= now and (not item.expires_at or item.expires_at > now)
        total_reads += item.read_count

    published_count = sum(1 for item in announcements if item.is_published)
    live_count = sum(1 for item in announcements if item.is_live)
    possible_reads = student_count * len([item for item in announcements if item.is_published])
    overall_read_rate = round((total_reads / possible_reads) * 100) if possible_reads else 0

    return render(request, "admin_ui/announcements.html", _base_context(
        announcements=announcements,
        priorities=Announcement.Priority.choices,
        live_count=live_count,
        published_count=published_count,
        student_count=student_count,
        overall_read_rate=overall_read_rate,
        now=now,
    ))


@admin_required
def admin_messages(request):
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        ids = [value for value in request.POST.getlist("message_ids") if str(value).isdigit()]
        qs = InternalMessage.objects.filter(id__in=ids, admin_deleted_at__isnull=True)

        if not ids:
            messages.error(request, "처리할 메시지를 선택해주세요.")
            return _redirect_back(request, "admin_messages")

        if action == "recall":
            recallable = qs.filter(read_at__isnull=True, recalled_at__isnull=True)
            count = recallable.update(recalled_at=timezone.now(), updated_at=timezone.now())
            blocked = qs.count() - count
            if count:
                messages.success(request, f"읽지 않은 메시지 {count}건을 회수했습니다.")
            if blocked:
                messages.warning(request, f"{blocked}건은 이미 읽었거나 회수된 메시지라 회수하지 않았습니다.")
        elif action == "delete":
            count = qs.update(admin_deleted_at=timezone.now(), updated_at=timezone.now())
            messages.success(request, f"보낸 메시지 기록 {count}건을 목록에서 삭제했습니다.")
        else:
            messages.error(request, "지원하지 않는 메시지 작업입니다.")
        return _redirect_back(request, "admin_messages")

    messages_qs = InternalMessage.objects.select_related("recipient__user", "sender").filter(admin_deleted_at__isnull=True)
    q = (request.GET.get("q") or "").strip()
    if q:
        messages_qs = messages_qs.filter(
            Q(title__icontains=q) | Q(body__icontains=q) | Q(recipient__user__first_name__icontains=q) | Q(recipient__user__username__icontains=q)
        )
    paginator = Paginator(messages_qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    active_messages = InternalMessage.objects.filter(admin_deleted_at__isnull=True)
    return render(request, "admin_ui/messages.html", _base_context(
        page_obj=page_obj,
        internal_messages=page_obj.object_list,
        q=q,
        total_count=active_messages.count(),
        unread_count=active_messages.filter(read_at__isnull=True, recalled_at__isnull=True).count(),
        recalled_count=active_messages.filter(recalled_at__isnull=False).count(),
    ))


@admin_required
def admin_activity_logs(request):
    if request.method == "POST":
        mode = (request.POST.get("cleanup_mode") or "").strip()
        cutoff = None
        if mode in {"30", "90", "180"}:
            cutoff = timezone.now() - timedelta(days=int(mode))
        elif mode == "custom":
            raw = (request.POST.get("cleanup_before") or "").strip()
            try:
                cutoff = timezone.make_aware(datetime.strptime(raw, "%Y-%m-%d"))
            except ValueError:
                messages.error(request, "정리 기준 날짜를 올바르게 입력해주세요.")
                return _redirect_back(request, "admin_activity_logs")
        else:
            messages.error(request, "로그 정리 범위를 선택해주세요.")
            return _redirect_back(request, "admin_activity_logs")

        delete_qs = AdminActivityLog.objects.filter(created_at__lt=cutoff)
        deleted = delete_qs.count()
        delete_qs.delete()
        messages.success(request, f"{timezone.localtime(cutoff):%Y-%m-%d} 이전 활동 로그 {deleted}건을 정리했습니다.")
        return _redirect_back(request, "admin_activity_logs")

    logs = AdminActivityLog.objects.select_related("actor").all()

    q = request.GET.get("q", "").strip()
    action = request.GET.get("action", "").strip()
    actor_id = request.GET.get("actor", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if q:
        logs = logs.filter(
            Q(action_label__icontains=q)
            | Q(description__icontains=q)
            | Q(path__icontains=q)
            | Q(actor__username__icontains=q)
            | Q(actor__first_name__icontains=q)
            | Q(actor__last_name__icontains=q)
            | Q(target_id__icontains=q)
        )
    if action:
        logs = logs.filter(action_key=action)
    if actor_id.isdigit():
        logs = logs.filter(actor_id=int(actor_id))
    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
            start = timezone.make_aware(start)
            logs = logs.filter(created_at__gte=start)
        except ValueError:
            pass
    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            end = timezone.make_aware(end)
            logs = logs.filter(created_at__lt=end)
        except ValueError:
            pass

    total_count = logs.count()
    today = timezone.localdate()
    today_count = AdminActivityLog.objects.filter(created_at__date=today).count()
    week_start = timezone.now() - timedelta(days=7)
    week_count = AdminActivityLog.objects.filter(created_at__gte=week_start).count()
    actor_count = AdminActivityLog.objects.filter(actor__isnull=False).values("actor_id").distinct().count()

    action_choices = list(
        AdminActivityLog.objects.values("action_key", "action_label")
        .order_by("action_label")
        .distinct()
    )
    actors = User.objects.filter(admin_activity_logs__isnull=False).distinct().order_by("username")

    paginator = Paginator(logs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "admin_ui/activity_logs.html", _base_context(
        page_obj=page_obj,
        logs=page_obj.object_list,
        q=q, action=action, actor_id=actor_id, date_from=date_from, date_to=date_to,
        action_choices=action_choices, actors=actors,
        total_count=total_count, today_count=today_count, week_count=week_count, actor_count=actor_count,
    ))


def _referenced_media_paths():
    """DB에서 실제로 참조 중인 업로드 파일 경로를 모은다."""
    refs = set()
    file_sources = (
        Assignment.objects.exclude(attachment="").values_list("attachment", flat=True),
        TeamAssignmentSubmission.objects.exclude(attachment="").values_list("attachment", flat=True),
        StudentAssignmentSubmission.objects.exclude(attachment="").values_list("attachment", flat=True),
        HRTask.objects.exclude(attachment="").values_list("attachment", flat=True),
        HRTaskSubmission.objects.exclude(attachment="").values_list("attachment", flat=True),
    )
    for source in file_sources:
        for name in source:
            if name:
                refs.add(str(name).replace("\\", "/").lstrip("/"))
    return refs


def _orphan_media_files():
    """DB 어느 레코드에서도 참조하지 않는 media 파일만 반환한다."""
    from pathlib import Path

    media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
    if not media_root.exists():
        return []

    referenced = _referenced_media_paths()
    orphaned = []
    for file_path in media_root.rglob("*"):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(media_root).as_posix()
        if relative not in referenced:
            orphaned.append(file_path)
    return orphaned


@admin_required
def admin_data_management(request):
    """관리자가 전체 운영 데이터의 백업 상태를 확인하는 화면."""
    model_counts = [
        ("수강생", Student.objects.count()),
        ("평가 회차", EvaluationRound.objects.count()),
        ("과제", Assignment.objects.count()),
        ("팀", Team.objects.count()),
        ("팀 배정", TeamMembership.objects.count()),
        ("조별과제 제출", TeamAssignmentSubmission.objects.count()),
        ("개별과제 제출", StudentAssignmentSubmission.objects.count()),
        ("발표 출결", RoundAttendance.objects.count()),
        ("평가 템플릿", EvaluationTemplate.objects.count()),
        ("팀 평가", TeamEvaluation.objects.count()),
        ("개인 평가", PersonalEvaluation.objects.count()),
        ("학생 결과", StudentResult.objects.count()),
        ("공지", Announcement.objects.filter(target_all=True).count()),
        ("내부 메시지", InternalMessage.objects.count()),
        ("활동 로그", AdminActivityLog.objects.count()),
    ]
    total_records = sum(value for _, value in model_counts)
    media_files = []
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if media_root:
        from pathlib import Path
        root = Path(media_root)
        if root.exists():
            media_files = [p for p in root.rglob("*") if p.is_file()]

    orphan_media_files = _orphan_media_files()
    return render(request, "admin_ui/data_management.html", _base_context(
        model_counts=model_counts,
        total_records=total_records,
        media_file_count=len(media_files),
        media_total_bytes=sum(p.stat().st_size for p in media_files),
        orphan_media_count=len(orphan_media_files),
        orphan_media_bytes=sum(p.stat().st_size for p in orphan_media_files),
    ))


@admin_required
@require_POST
def admin_media_cleanup(request):
    """DB에서 참조하지 않는 누적 업로드 파일을 안전하게 삭제한다."""
    confirmation = (request.POST.get("confirmation") or "").strip()
    if confirmation != "CLEAN":
        messages.error(request, "안전 확인란에 CLEAN을 정확히 입력해야 정리할 수 있습니다.")
        return _redirect_back(request, "admin_data_management")

    orphaned = _orphan_media_files()
    deleted_count = 0
    deleted_bytes = 0
    media_root = Path(getattr(settings, "MEDIA_ROOT", ""))

    for file_path in orphaned:
        try:
            size = file_path.stat().st_size
            file_path.unlink()
            deleted_count += 1
            deleted_bytes += size
        except OSError:
            continue

    # 비어 있는 하위 폴더만 정리한다. MEDIA_ROOT 자체는 유지한다.
    if media_root.exists():
        directories = sorted(
            [path for path in media_root.rglob("*") if path.is_dir()],
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass

    AdminActivityLog.objects.create(
        user=request.user,
        action="media_cleanup",
        description=f"미참조 업로드 파일 {deleted_count}개 정리 ({deleted_bytes} bytes)",
    )
    messages.success(
        request,
        f"사용되지 않는 업로드 파일 {deleted_count}개를 정리했습니다.",
    )
    return _redirect_back(request, "admin_data_management")


@admin_required
def admin_data_backup_download(request):
    """User + dashboard 앱 데이터를 JSON으로 직렬화하고 media 파일과 함께 ZIP으로 내려준다."""
    import json
    import zipfile
    from itertools import chain
    from pathlib import Path
    from django.core import serializers

    # FK 의존 순서대로 직렬화한다. 사용자 비밀번호는 원문이 아니라 Django 해시 형태로만 포함된다.
    objects = list(chain(
        User.objects.all().order_by("id"),
        Student.objects.all().order_by("id"),
        EvaluationRound.objects.all().order_by("id"),
        Assignment.objects.all().order_by("id"),
        Team.objects.all().order_by("id"),
        TeamMembership.objects.all().order_by("id"),
        TeamAssignmentSubmission.objects.all().order_by("id"),
        StudentAssignmentSubmission.objects.all().order_by("id"),
        RoundAttendance.objects.all().order_by("id"),
        EvaluationTemplate.objects.all().order_by("id"),
        EvaluationCriterion.objects.all().order_by("id"),
        TeamEvaluation.objects.all().order_by("id"),
        TeamEvaluationScore.objects.all().order_by("id"),
        PersonalEvaluation.objects.all().order_by("id"),
        PersonalEvaluationScore.objects.all().order_by("id"),
        TeamResult.objects.all().order_by("id"),
        StudentResult.objects.all().order_by("id"),
        ResultPublishSetting.objects.all().order_by("id"),
        Announcement.objects.all().order_by("id"),
        AnnouncementRead.objects.all().order_by("id"),
        InternalMessage.objects.all().order_by("id"),
        AdminActivityLog.objects.all().order_by("id"),
    ))

    serialized = json.loads(serializers.serialize("json", objects))
    payload = {
        "format": "ax-evaluation-backup",
        "version": 1,
        "created_at": timezone.now().isoformat(),
        "object_count": len(serialized),
        "objects": serialized,
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "data.json",
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "README.txt",
            (
                "AX 평가 시스템 백업 파일\n"
                "- data.json: 사용자/평가/팀/결과/공지/활동 로그 데이터\n"
                "- media/: 과제 첨부파일 등 업로드 파일\n"
                "주의: 사용자 비밀번호 해시 등 민감한 데이터가 포함될 수 있으므로 외부 공유 금지\n"
            ).encode("utf-8"),
        )
        media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
        if media_root.exists():
            for file_path in media_root.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, f"media/{file_path.relative_to(media_root).as_posix()}")

    filename = timezone.localtime().strftime("ax_backup_%Y%m%d_%H%M%S.zip")
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

@admin_required
@require_POST
def admin_data_restore(request):
    """STEP 17 백업 ZIP을 검증한 뒤 DB 운영 데이터를 전체 교체한다."""
    import json
    import zipfile
    from pathlib import Path, PurePosixPath
    from django.core import serializers

    upload = request.FILES.get("backup_file")
    confirmation = request.POST.get("confirmation", "").strip()
    if not upload:
        messages.error(request, "복원할 백업 ZIP 파일을 선택해주세요.")
        return _redirect_back(request, "admin_data_management")
    if confirmation != "RESTORE":
        messages.error(request, "안전 확인란에 RESTORE를 정확히 입력해야 복원할 수 있습니다.")
        return _redirect_back(request, "admin_data_management")
    if upload.size > 100 * 1024 * 1024:
        messages.error(request, "백업 파일은 100MB 이하만 업로드할 수 있습니다.")
        return _redirect_back(request, "admin_data_management")

    raw = upload.read()
    try:
        with zipfile.ZipFile(BytesIO(raw), "r") as archive:
            if "data.json" not in archive.namelist():
                raise ValueError("data.json이 없습니다.")
            payload = json.loads(archive.read("data.json").decode("utf-8"))
            if payload.get("format") != "ax-evaluation-backup" or payload.get("version") != 1:
                raise ValueError("지원하지 않는 백업 형식입니다.")
            object_list = payload.get("objects")
            if not isinstance(object_list, list):
                raise ValueError("백업 데이터 형식이 올바르지 않습니다.")

            # 관리자 본인 계정도 백업에 있는지 먼저 확인한다. 복원 뒤 로그인 세션이 끊기는 사고를 막는다.
            current_pk = request.user.pk
            backup_user_pks = {
                item.get("pk") for item in object_list if item.get("model") == "auth.user"
            }
            if current_pk not in backup_user_pks:
                raise ValueError("현재 로그인한 관리자 계정이 백업에 없어 안전상 복원을 중단했습니다.")

            serialized_json = json.dumps(object_list, ensure_ascii=False)
            # deserialize를 DB 삭제 전에 먼저 수행해 모델/필드 호환성 오류를 검증한다.
            deserialized = list(serializers.deserialize("json", serialized_json))

            with transaction.atomic():
                # 자식 -> 부모 순서로 제거한다.
                AdminActivityLog.objects.all().delete()
                AnnouncementRead.objects.all().delete()
                Announcement.objects.all().delete()
                ResultPublishSetting.objects.all().delete()
                StudentResult.objects.all().delete()
                TeamResult.objects.all().delete()
                PersonalEvaluationScore.objects.all().delete()
                PersonalEvaluation.objects.all().delete()
                TeamEvaluationScore.objects.all().delete()
                TeamEvaluation.objects.all().delete()
                EvaluationCriterion.objects.all().delete()
                EvaluationTemplate.objects.all().delete()
                RoundAttendance.objects.all().delete()
                StudentAssignmentSubmission.objects.all().delete()
                TeamAssignmentSubmission.objects.all().delete()
                TeamMembership.objects.all().delete()
                Team.objects.all().delete()
                Assignment.objects.all().delete()
                EvaluationRound.objects.all().delete()
                Student.objects.all().delete()
                User.objects.all().delete()

                for deserialized_object in deserialized:
                    deserialized_object.save()

            # DB transaction 성공 뒤 media 파일을 복원한다. 경로 traversal을 차단한다.
            media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
            if media_root:
                media_root.mkdir(parents=True, exist_ok=True)
                for member in archive.infolist():
                    if member.is_dir() or not member.filename.startswith("media/"):
                        continue
                    relative = PurePosixPath(member.filename).relative_to("media")
                    if ".." in relative.parts:
                        continue
                    destination = media_root.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as src, open(destination, "wb") as dst:
                        dst.write(src.read())

        messages.success(request, f"백업 복원이 완료되었습니다. {len(object_list):,}개 레코드를 복원했습니다.")
        return redirect("admin_data_management")
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        messages.error(request, f"백업 파일을 복원할 수 없습니다: {exc}")
        return _redirect_back(request, "admin_data_management")
    except Exception as exc:
        messages.error(request, f"복원 중 오류가 발생했습니다: {exc}")
        return _redirect_back(request, "admin_data_management")
