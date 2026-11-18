{{- define "optional-cloud-logging.validate" -}}
{{- if .Values.enabled -}}
{{- $namespace := required "namespace must name the dedicated application namespace" .Values.namespace -}}
{{- $release := required "releaseName must name the separate integration release" .Values.releaseName -}}
{{- if ne $namespace .Release.Namespace -}}
{{- fail "namespace must equal the Helm release namespace" -}}
{{- end -}}
{{- if ne $release .Release.Name -}}
{{- fail "releaseName must equal the Helm release name" -}}
{{- end -}}
{{- if has $namespace (list "default" "kube-system" "kube-public" "kube-node-lease" "kyma-system" "istio-system") -}}
{{- fail "use a dedicated application namespace, not a default or system namespace" -}}
{{- end -}}
{{- if not .Values.ownershipConfirmed -}}
{{- fail "ownershipConfirmed must confirm delegated ownership of these cluster-scoped pipelines" -}}
{{- end -}}
{{- $version := required "telemetryModuleVersion must record the checked installed version" .Values.telemetryModuleVersion -}}
{{- if not (semverCompare ">=1.52.0" $version) -}}
{{- fail "Telemetry module 1.52.0 or later is required for OTTL pipelines" -}}
{{- end -}}
{{- $_ := required "backendSecret.name must reference an existing approved Secret" .Values.backendSecret.name -}}
{{- end -}}
{{- end -}}

{{- define "optional-cloud-logging.scope" -}}
{{- $scope := printf "%s/%s" .Values.namespace .Values.releaseName -}}
{{- printf "cb-cl-%s-%s-%s" (.Values.namespace | trunc 18 | trimSuffix "-") (.Values.releaseName | trunc 18 | trimSuffix "-") ($scope | sha256sum | trunc 8) -}}
{{- end -}}

{{- define "optional-cloud-logging.name" -}}
{{- printf "%s-%s" (include "optional-cloud-logging.scope" .root) .signal -}}
{{- end -}}

{{- define "optional-cloud-logging.assertOwned" -}}
{{- if .existing -}}
{{- $annotations := dig "metadata" "annotations" (dict) .existing -}}
{{- $labels := dig "metadata" "labels" (dict) .existing -}}
{{- if or (ne (get $annotations "meta.helm.sh/release-name") .root.Release.Name) (ne (get $annotations "meta.helm.sh/release-namespace") .root.Release.Namespace) (ne (get $labels "app.kubernetes.io/managed-by") "Helm") (ne (get $labels "cookbook.sap.com/integration") "optional-cloud-logging") -}}
{{- fail "pipeline name conflict: preserve the existing object; do not adopt or take ownership" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "optional-cloud-logging.output" -}}
otlp:
  protocol: grpc
  endpoint:
    valueFrom:
      secretKeyRef:
        namespace: {{ .Values.namespace | quote }}
        name: {{ .Values.backendSecret.name | quote }}
        key: {{ .Values.backendSecret.endpointKey | quote }}
  tls:
    cert:
      valueFrom:
        secretKeyRef:
          namespace: {{ .Values.namespace | quote }}
          name: {{ .Values.backendSecret.name | quote }}
          key: {{ .Values.backendSecret.certificateKey | quote }}
    key:
      valueFrom:
        secretKeyRef:
          namespace: {{ .Values.namespace | quote }}
          name: {{ .Values.backendSecret.name | quote }}
          key: {{ .Values.backendSecret.privateKeyKey | quote }}
{{- end -}}
