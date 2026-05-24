import client from './client'
import type {
  Wirtschaftsjahr,
  FolgejahrPreviewResponse,
  FolgejahrCommitResponse,
} from '../types'

export const wirtschaftsjahreApi = {
  list: (params?: { objekt?: string; status?: string }) =>
    client.get<Wirtschaftsjahr[]>('/wirtschaftsjahre/', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Wirtschaftsjahr>(`/wirtschaftsjahre/${id}/`).then(r => r.data),

  folgejahrPreview: (objektIds: string[]) =>
    client
      .post<FolgejahrPreviewResponse>('/wirtschaftsjahre/folgejahr/preview/', { objekt_ids: objektIds })
      .then(r => r.data),

  folgejahrCommit: (objektIds: string[]) =>
    client
      .post<FolgejahrCommitResponse>('/wirtschaftsjahre/folgejahr/commit/', { objekt_ids: objektIds })
      .then(r => r.data),
}
