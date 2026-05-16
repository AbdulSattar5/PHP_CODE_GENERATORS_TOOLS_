import json
import logging
import time
from typing import List, Tuple

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings
from rest_framework.test import APIClient

from models.project import Project


DEFAULT_PROMPTS: List[Tuple[str, str]] = [
    (
        "Customer",
        "Create complete Customer form with fields: cust_id, cust_name, mobile, address",
    ),
    (
        "Student",
        "Create complete Student form with fields: Id, txtRollNo, txtStudentName, txtClass, txtmode, CTRL_HID_VALUE",
    ),
    (
        "Supplier",
        "Create complete Supplier form with fields: supp_id, supp_name, contact_no, city",
    ),
]


class Command(BaseCommand):
    help = "Run Phase-2 end-to-end smoke benchmark against /api/generate/."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True, help="Authenticated user id")
        parser.add_argument("--project-id", type=str, required=True, help="Project UUID")
        parser.add_argument(
            "--codebase-id",
            type=str,
            default="",
            help="Optional explicit codebase UUID. Omit to test auto-selection.",
        )
        parser.add_argument(
            "--prompts-file",
            type=str,
            default="",
            help="Optional JSON file containing prompts. Expected list of strings or {label,prompt} objects.",
        )
        parser.add_argument(
            "--use-company-patterns",
            action="store_true",
            default=True,
            help="Use company pattern retrieval (default: true).",
        )
        parser.add_argument(
            "--no-company-patterns",
            action="store_true",
            help="Disable company pattern retrieval.",
        )
        parser.add_argument(
            "--show-logs",
            action="store_true",
            help="Show backend INFO/WARNING logs during smoke run (default: hidden).",
        )

    def _load_prompts(self, prompts_file: str) -> List[Tuple[str, str]]:
        if not prompts_file:
            return DEFAULT_PROMPTS

        try:
            with open(prompts_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            raise CommandError(f"Unable to read prompts file '{prompts_file}': {exc}") from exc

        if not isinstance(payload, list) or not payload:
            raise CommandError("Prompts file must contain a non-empty JSON array.")

        resolved: List[Tuple[str, str]] = []
        for index, item in enumerate(payload, start=1):
            if isinstance(item, str):
                resolved.append((f"Prompt{index}", item))
                continue
            if isinstance(item, dict):
                prompt = str(item.get("prompt") or "").strip()
                label = str(item.get("label") or f"Prompt{index}").strip() or f"Prompt{index}"
                if prompt:
                    resolved.append((label, prompt))
                    continue
            raise CommandError(
                "Each prompt item must be either a string or an object with 'prompt' (and optional 'label')."
            )

        return resolved

    def handle(self, *args, **options):
        user_id = options["user_id"]
        project_id = options["project_id"]
        codebase_id = str(options.get("codebase_id") or "").strip()
        use_company_patterns = bool(options.get("use_company_patterns", True))
        if options.get("no_company_patterns"):
            use_company_patterns = False
        quiet_logs = not bool(options.get("show_logs"))

        prompts = self._load_prompts(str(options.get("prompts_file") or "").strip())

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found: {user_id}") from exc

        try:
            project = Project.objects.get(id=project_id, user=user)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project not found for user {user_id}: {project_id}") from exc

        client = APIClient()
        client.force_authenticate(user=user)

        success_count = 0
        fallback_count = 0
        durations = []

        self.stdout.write(
            f"Running Phase-2 smoke benchmark | user={user_id} project={project.id} "
            f"codebase={'auto' if not codebase_id else codebase_id}"
        )

        previous_disable_level = logging.root.manager.disable
        if quiet_logs:
            logging.disable(logging.CRITICAL)
        try:
            with override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"]):
                for label, prompt in prompts:
                    started_at = time.time()
                    payload = {
                        "user_request": prompt,
                        "project_id": str(project.id),
                        "use_company_patterns": use_company_patterns,
                        "use_standards": True,
                        "auto_execute_sql": False,
                    }
                    if codebase_id:
                        payload["codebase_id"] = codebase_id

                    response = client.post("/api/generate/", payload, format="json")
                    elapsed = round(time.time() - started_at, 2)
                    durations.append(elapsed)

                    try:
                        data = response.json()
                    except Exception:
                        data = {}

                    status_value = str(data.get("status") or "").lower()
                    fallback_used = bool(data.get("fallback_used"))
                    validation_score = data.get("validation_score")
                    metadata = data.get("metadata") or {}
                    inline_meta = metadata.get("inline_generation_metadata") or {}
                    attempts = metadata.get("attempts_made") or inline_meta.get("attempts_made")
                    models = inline_meta.get("attempt_models") or metadata.get("attempt_models")

                    if status_value == "success" and not fallback_used:
                        success_count += 1
                    if fallback_used:
                        fallback_count += 1

                    self.stdout.write(
                        f"RUN {label} | HTTP={response.status_code} STATUS={status_value or 'unknown'} "
                        f"FALLBACK={fallback_used} VAL={validation_score} ATTEMPTS={attempts} "
                        f"MODELS={models} TIME={elapsed}s"
                    )
        finally:
            logging.disable(previous_disable_level)

        total = len(prompts)
        average_time = round(sum(durations) / total, 2) if durations else 0.0
        success_rate = round((success_count / total) * 100.0, 2) if total else 0.0
        fallback_rate = round((fallback_count / total) * 100.0, 2) if total else 0.0

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"SUMMARY_SUCCESS {success_count}/{total} ({success_rate}%)"))
        self.stdout.write(self.style.WARNING(f"SUMMARY_FALLBACK {fallback_count}/{total} ({fallback_rate}%)"))
        self.stdout.write(f"SUMMARY_AVG_TIME {average_time}s")
