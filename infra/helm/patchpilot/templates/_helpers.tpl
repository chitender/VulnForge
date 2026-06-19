{{/*
Expand the name of the chart.
*/}}
{{- define "patchpilot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name — used as prefix for all resource names.
*/}}
{{- define "patchpilot.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "patchpilot.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
Selector labels — must be stable and match both Deployment and Service.
*/}}
{{- define "patchpilot.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
PostgreSQL sync URL (psycopg2) for Alembic migrations and Celery workers.
Derived from bundled subchart when postgresql.enabled=true.
*/}}
{{- define "patchpilot.databaseUrl" -}}
{{- if .Values.postgresql.enabled -}}
{{- $pgPass := required "postgresql.auth.password must be set (--set postgresql.auth.password=<strong-password>)" .Values.postgresql.auth.password -}}
postgresql+psycopg2://{{ .Values.postgresql.auth.username }}:{{ $pgPass }}@{{ .Release.Name }}-postgresql:5432/{{ .Values.postgresql.auth.database }}
{{- else -}}
{{ required "Set externalDatabaseUrl when postgresql.enabled=false" .Values.externalDatabaseUrl }}
{{- end }}
{{- end }}

{{/*
PostgreSQL async URL (asyncpg) for FastAPI.
*/}}
{{- define "patchpilot.databaseUrlAsync" -}}
{{- include "patchpilot.databaseUrl" . | replace "+psycopg2" "+asyncpg" }}
{{- end }}

{{/*
Redis URL — bundled subchart or external.
*/}}
{{- define "patchpilot.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ .Release.Name }}-redis-master:6379/0
{{- else -}}
{{ required "Set externalRedisUrl when redis.enabled=false" .Values.externalRedisUrl }}
{{- end }}
{{- end }}

{{/*
Keycloak base URL — bundled subchart or external.
*/}}
{{- define "patchpilot.keycloakUrl" -}}
{{- if .Values.keycloak.enabled -}}
http://{{ .Release.Name }}-keycloak:80
{{- else -}}
{{ required "Set externalKeycloakUrl when keycloak.enabled=false" .Values.externalKeycloakUrl }}
{{- end }}
{{- end }}

{{/*
Trivy server URL (always internal).
*/}}
{{- define "patchpilot.trivyServerUrl" -}}
http://{{ include "patchpilot.fullname" . }}-trivy-server:4954
{{- end }}
