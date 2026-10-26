{{- define "urumi.foundationName" -}}
{{- printf "%s-foundation" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "urumi.foundationSelectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: foundation
{{- end -}}

{{- define "urumi.foundationLabels" -}}
{{ include "urumi.foundationSelectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "urumi.foundationImage" -}}
{{- if .Values.foundation.image.digest -}}
{{ printf "%s@%s" .Values.foundation.image.repository .Values.foundation.image.digest }}
{{- else -}}
{{ printf "%s:%s" .Values.foundation.image.repository .Values.foundation.image.tag }}
{{- end -}}
{{- end -}}
