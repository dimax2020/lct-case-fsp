declare module 'monaco-editor/esm/vs/editor/editor.worker?worker' {
  const WorkerFactory: new () => Worker
  export default WorkerFactory
}

declare module 'monaco-editor/esm/vs/basic-languages/python/python.contribution'
declare module 'monaco-editor/esm/vs/basic-languages/go/go.contribution'
