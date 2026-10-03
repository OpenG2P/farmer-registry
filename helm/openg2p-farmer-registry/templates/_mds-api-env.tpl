{{/*
Master Data API env for the analytics Jobs: the same MDS_* variables the
platform's db-seed Job gets, read by /seed/mds_client.py. These Jobs read
Master Data (the geography) through its API with a client-credentials token as
this registry's own Keycloak client — never Master Data's database.
*/}}
{{- define "fr.mdsApiEnv" -}}
- name: MDS_API_URL
  value: {{ tpl .Values.global.masterDataApiUrl . | quote }}
- name: MDS_TOKEN_URL
  value: {{ tpl .Values.global.masterDataTokenUrl . | quote }}
- name: MDS_CLIENT_ID
  value: {{ tpl .Values.global.authClientId . | quote }}
- name: MDS_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ tpl .Values.global.authClientSecret . | quote }}
      key: {{ tpl .Values.global.authClientSecretKey . | quote }}
{{- end }}
