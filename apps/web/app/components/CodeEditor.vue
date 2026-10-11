<script setup lang="ts">
import type * as Monaco from 'monaco-editor'

const props = defineProps<{ language: string; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const host = ref<HTMLElement | null>(null)
let editor: Monaco.editor.IStandaloneCodeEditor | null = null
let monacoApi: typeof Monaco | null = null

function monacoLang(lang: string) {
  return lang === 'go' ? 'go' : 'python'
}

onMounted(async () => {
  const workerMod = await import('monaco-editor/esm/vs/editor/editor.worker?worker')
  const monaco = await import('monaco-editor')
  await import('monaco-editor/esm/vs/basic-languages/python/python.contribution')
  await import('monaco-editor/esm/vs/basic-languages/go/go.contribution')
  monacoApi = monaco
  const env = globalThis as typeof globalThis & { MonacoEnvironment?: { getWorker: () => Worker } }
  env.MonacoEnvironment = { getWorker: () => new workerMod.default() }
  if (!host.value) return
  editor = monaco.editor.create(host.value, {
    value: props.modelValue,
    language: monacoLang(props.language),
    theme: 'vs-dark',
    minimap: { enabled: false },
    fontSize: 14,
    automaticLayout: true,
    scrollBeyondLastLine: false,
  })
  editor.onDidChangeModelContent(() => {
    if (!editor) return
    emit('update:modelValue', editor.getValue())
  })
})

watch(() => props.modelValue, (value) => {
  if (editor && editor.getValue() !== value) editor.setValue(value)
})

watch(() => props.language, (lang) => {
  const model = editor?.getModel()
  if (model && monacoApi) monacoApi.editor.setModelLanguage(model, monacoLang(lang))
})

onBeforeUnmount(() => editor?.dispose())
</script>

<template>
  <div ref="host" style="height: 280px; border: 1px solid var(--line-strong);" />
</template>
