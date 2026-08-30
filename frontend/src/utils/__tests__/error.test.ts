import { describe, expect, it } from 'vite-plus/test'
import { ApiError, defaultTitleFor, formatHttpError, normalizeHttpError } from '@/utils/error'
import type { HttpValidationError } from '@/client/types.gen'

describe('formatHttpError', () => {
  it('joins HttpValidationError detail msgs with ；', () => {
    const err: HttpValidationError = {
      detail: [
        { loc: ['body', 'duration'], msg: 'duration must be > 0', type: 'value_error' },
        { loc: ['body', 'name'], msg: 'name is required', type: 'value_error' },
      ],
    }
    expect(formatHttpError(err)).toBe('duration must be > 0；name is required')
  })

  it('returns Error.message when no detail', () => {
    expect(formatHttpError(new Error('网络超时'))).toBe('网络超时')
  })

  it('returns fallback for null/undefined', () => {
    expect(formatHttpError(null)).toBe('操作失败，请重试')
    expect(formatHttpError(undefined)).toBe('操作失败，请重试')
    expect(formatHttpError({})).toBe('操作失败，请重试')
  })

  it('returns fallback for empty detail array', () => {
    expect(formatHttpError({ detail: [] })).toBe('操作失败，请重试')
  })

  it('skips empty msg strings', () => {
    const err: HttpValidationError = {
      detail: [
        { loc: ['body'], msg: '', type: 'value_error' },
        { loc: ['body', 'name'], msg: 'name is required', type: 'value_error' },
      ],
    }
    expect(formatHttpError(err)).toBe('name is required')
  })

  it('uses custom fallback', () => {
    expect(formatHttpError(null, '删除失败，请重试')).toBe('删除失败，请重试')
  })

  it('returns string detail directly (FastAPI HTTPException)', () => {
    expect(formatHttpError({ detail: 'Resource not found' })).toBe('Resource not found')
  })

  it('returns fallback for empty string detail', () => {
    expect(formatHttpError({ detail: '' })).toBe('操作失败，请重试')
  })

  it('returns ApiError.message when given an ApiError instance', () => {
    const err = new ApiError('提交内容有误', 422, [], '/task', 'POST', true, false)
    expect(formatHttpError(err)).toBe('提交内容有误')
  })

  it('returns fallback when ApiError.message is empty', () => {
    const err = new ApiError('', 500, null, '/task', 'POST', false, false)
    expect(formatHttpError(err, '兜底文案')).toBe('兜底文案')
  })
})

describe('normalizeHttpError', () => {
  it('returns network error for status 0', () => {
    const err = normalizeHttpError(undefined, 0, 'POST', '/task')
    expect(err.isNetwork).toBe(true)
    expect(err.message).toBe('网络异常，请检查连接后重试')
    expect(err.endpoint).toBe('/task')
    expect(err.method).toBe('POST')
  })

  it('joins 422 array detail into message', () => {
    const err = normalizeHttpError(
      { detail: [{ msg: 'a is bad' }, { msg: 'b is bad' }] },
      422,
      'POST',
      '/task',
    )
    expect(err.isValidation).toBe(true)
    expect(err.message).toBe('a is bad；b is bad')
  })

  it('returns string detail directly for non-422', () => {
    const err = normalizeHttpError({ detail: 'Not Found' }, 404, 'GET', '/project/1')
    expect(err.status).toBe(404)
    expect(err.message).toBe('Not Found')
    expect(err.isValidation).toBe(false)
  })

  it('falls back to HTTP status when detail unrecognizable', () => {
    const err = normalizeHttpError({}, 500, 'POST', '/task')
    expect(err.message).toBe('操作失败（HTTP 500）')
  })
})

describe('defaultTitleFor', () => {
  it('maps status codes to semantic Chinese titles', () => {
    expect(defaultTitleFor(422, 'POST', '/task')).toBe('提交内容有误')
    expect(defaultTitleFor(401, 'GET', '/me')).toBe('请先登录')
    expect(defaultTitleFor(403, 'POST', '/task')).toBe('没有权限')
    expect(defaultTitleFor(404, 'GET', '/task/1')).toBe('资源不存在')
    expect(defaultTitleFor(409, 'POST', '/task')).toBe('操作冲突')
    expect(defaultTitleFor(0, 'GET', '/task')).toBe('网络异常')
    expect(defaultTitleFor(502, 'GET', '/task')).toBe('服务器异常')
  })

  it('maps common endpoints to specific Chinese titles', () => {
    expect(defaultTitleFor(400, 'POST', '/task')).toBe('创建任务失败')
    expect(defaultTitleFor(400, 'PUT', '/task/1')).toBe('更新任务失败')
    expect(defaultTitleFor(400, 'DELETE', '/task/1')).toBe('删除任务失败')
    expect(defaultTitleFor(400, 'POST', '/optimize-record')).toBe('启动优化失败')
    expect(defaultTitleFor(400, 'DELETE', '/optimize-record/1')).toBe('停止优化失败')
    expect(defaultTitleFor(400, 'POST', '/project')).toBe('创建项目失败')
    expect(defaultTitleFor(400, 'DELETE', '/project/1')).toBe('删除项目失败')
  })

  it('falls back to 操作失败 for unknown endpoints', () => {
    expect(defaultTitleFor(400, 'GET', '/unknown/path')).toBe('操作失败')
  })
})
