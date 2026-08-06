{{/*
Name of the ConfigMap carrying this registry's Insights maps content.
Set insightMaps.build.content.configMap in the Insights chart to this value.
*/}}
{{- define "mapsContent.name" -}}
{{- default (printf "%s-maps-content" .Release.Name) .Values.mapsContent.nameOverride -}}
{{- end -}}
