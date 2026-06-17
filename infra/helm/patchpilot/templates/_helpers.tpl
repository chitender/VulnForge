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
