<script setup lang="ts">
// Редактор кода для задач теста. В браузере подгружается Monaco (подсветка Python/Go, отступы,
// нумерация строк); пока он грузится или если загрузка не удалась — работает обычное поле ввода.
const props = defineProps<{ language: string; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const host = ref<HTMLElement>()
const ready = ref(false)
const { theme } = useTheme()

type Monaco = typeof import('monaco-editor/esm/vs/editor/editor.api')
type Editor = ReturnType<Monaco['editor']['create']>
let monaco: Monaco | null = null
let editor: Editor | null = null

function onInput(event: Event) {
  const target = event.target
  if (target instanceof HTMLTextAreaElement) emit('update:modelValue', target.value)
}

function onTab(event: KeyboardEvent) {
  if (event.key !== 'Tab' || event.shiftKey) return
  const target = event.target as HTMLTextAreaElement
  event.preventDefault()
  const { selectionStart: start, selectionEnd: end, value } = target
  const next = value.slice(0, start) + '    ' + value.slice(end)
  emit('update:modelValue', next)
  void nextTick(() => { target.selectionStart = target.selectionEnd = start + 4 })
}

const monacoLanguage = computed(() => (props.language === 'go' ? 'go' : 'python'))

onMounted(async () => {
  try {
    const [api, worker] = await Promise.all([
      import('monaco-editor/esm/vs/editor/editor.api'),
      import('monaco-editor/esm/vs/editor/editor.worker?worker'),
      import('monaco-editor/esm/vs/basic-languages/python/python.contribution'),
      import('monaco-editor/esm/vs/basic-languages/go/go.contribution'),
    ])
    const EditorWorker = worker.default
    ;(self as unknown as { MonacoEnvironment: { getWorker: () => Worker } }).MonacoEnvironment = {
      getWorker: () => new EditorWorker(),
    }
    monaco = api
    if (!host.value) return
    editor = api.editor.create(host.value, {
      value: props.modelValue,
      language: monacoLanguage.value,
      theme: theme.value === 'light' ? 'vs' : 'vs-dark',
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 14,
      tabSize: 4,
      scrollBeyondLastLine: false,
      ariaLabel: props.language === 'go' ? 'Код на Go' : 'Код на Python',
    })
    editor.onDidChangeModelContent(() => {
      const value = editor?.getValue() ?? ''
      if (value !== props.modelValue) emit('update:modelValue', value)
    })
    ready.value = true
  } catch {
    ready.value = false
  }
})

watch(() => props.modelValue, (value) => {
  if (editor && editor.getValue() !== value) editor.setValue(value)
})
watch(monacoLanguage, (lang) => {
  const model = editor?.getModel()
  if (model && monaco) monaco.editor.setModelLanguage(model, lang)
})
watch(theme, (value) => {
  monaco?.editor.setTheme(value === 'light' ? 'vs' : 'vs-dark')
})
onBeforeUnmount(() => {
  editor?.getModel()?.dispose()
  editor?.dispose()
})
</script>

<template>
  <div class="code-editor">
    <div v-show="ready" ref="host" class="code-editor-host" />
    <textarea
      v-if="!ready"
      :value="props.modelValue"
      :aria-label="props.language === 'go' ? 'Код на Go' : 'Код на Python'"
      spellcheck="false"
      autocomplete="off"
      class="code-editor-fallback"
      @input="onInput"
      @keydown="onTab"
    />
  </div>
</template>

<style>
.code-editor-host { width: 100%; height: 320px; border: 1px solid var(--line-strong); }
.code-editor-fallback { box-sizing: border-box; width: 100%; min-height: 280px; margin: 0; padding: 16px; resize: vertical; border: 1px solid var(--line-strong); background: var(--plate); color: var(--on-plate); font: 14px/22px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; tab-size: 4; }
</style>
