{{- define "production-order-agent.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 55 | trimSuffix "-" -}}
{{- end -}}

{{- define "production-order-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "production-order-agent.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{ include "production-order-agent.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "production-order-agent.image" -}}
{{- $repository := required "image.repository is required" .Values.image.repository -}}
{{- $tag := required "image.tag is required" .Values.image.tag -}}
{{- $digest := required "image.digest is required" .Values.image.digest -}}
{{- if eq $tag "latest" -}}
{{- fail "image.tag must not be latest" -}}
{{- end -}}
{{- printf "%s:%s@%s" $repository $tag $digest -}}
{{- end -}}

{{- define "production-order-agent.url" -}}
{{- if .Values.apirule.enabled -}}
{{- printf "https://%s" (required "apirule.host is required when apirule.enabled=true" .Values.apirule.host) -}}
{{- else -}}
{{- printf "http://%s-agent.%s.svc.cluster.local:8000" (include "production-order-agent.fullname" .) .Release.Namespace -}}
{{- end -}}
{{- end -}}
