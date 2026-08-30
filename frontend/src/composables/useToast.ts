import { toast } from 'vue-sonner'

export interface NotifyOptions {
  title: string
  description?: string
  duration?: number
}

// 内部核心函数
function createNotify(type: 'success' | 'error' | 'info' | 'warning', defaultDuration: number) {
  return (opts: NotifyOptions | string) => {
    const o = typeof opts === 'string' ? { title: opts } : opts
    toast[type](o.title, {
      description: o.description,
      duration: o.duration ?? defaultDuration,
    })
  }
}

export const notifySuccess = createNotify('success', 4000)
export const notifyError = createNotify('error', 5000)
export const notifyInfo = createNotify('info', 4000)
export const notifyWarning = createNotify('warning', 4500)

export function useToast() {
  return { notifySuccess, notifyError, notifyInfo, notifyWarning }
}
