"""Template context processors for GenCode AI."""

from models.project import Project


def sidebar_context(request):
    if not request.user.is_authenticated:
        return {}
    projects = Project.objects.filter(user=request.user).order_by('-updated_at')[:30]
    return {'sidebar_projects': projects}
