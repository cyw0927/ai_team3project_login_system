from django.contrib import admin

from .models import (
    Assignment,
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    ResultPublishSetting,
    Student,
    StudentResult,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
    TeamResult,
    Announcement,
    AnnouncementRead,
    TeamAssignmentSubmission,
)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "is_active", "affiliation")
    list_filter = ("is_active",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")


@admin.register(EvaluationRound)
class EvaluationRoundAdmin(admin.ModelAdmin):
    list_display = ("name", "start_at", "end_at", "status", "is_reopened")
    list_filter = ("status", "is_reopened")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "evaluation_round", "project_title", "is_active")
    list_filter = ("evaluation_round", "is_active")
    search_fields = ("name", "project_title")


@admin.register(EvaluationTemplate)
class EvaluationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "evaluation_type", "evaluation_round", "is_active")
    list_filter = ("evaluation_type", "is_active")


admin.site.register(Assignment)
admin.site.register(TeamMembership)
admin.site.register(EvaluationCriterion)
admin.site.register(TeamEvaluation)
admin.site.register(TeamEvaluationScore)
admin.site.register(PersonalEvaluation)
admin.site.register(PersonalEvaluationScore)
admin.site.register(TeamResult)
admin.site.register(StudentResult)
admin.site.register(ResultPublishSetting)

admin.site.register(Announcement)
admin.site.register(AnnouncementRead)

from .models import AdminActivityLog

admin.site.register(AdminActivityLog)


try:
    admin.site.register(TeamAssignmentSubmission)
except admin.sites.AlreadyRegistered:
    pass
