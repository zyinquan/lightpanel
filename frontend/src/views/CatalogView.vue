<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { SoftwareEntry } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { errorMessage, pushToast } from '@/composables/useToast'
import SoftwareCard from '@/components/SoftwareCard.vue'
import TagFilter from '@/components/TagFilter.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import { colorFromString, normalizeUrl } from '@/utils/format'

const selectedTags = ref<string[]>([])
const matchAll = ref(false)
const search = ref('')
const sort = ref<'order' | 'name' | 'recent'>('order')

const queryKey = computed(() =>
  JSON.stringify([selectedTags.value, matchAll.value, search.value, sort.value]),
)

const page = usePolling(
  () =>
    api.catalog({
      tags: selectedTags.value,
      matchAll: matchAll.value,
      search: search.value,
      sort: sort.value,
    }),
  { interval: 15000 },
)

watch(queryKey, () => page.refresh())

const entries = computed(() => page.data.value?.entries ?? [])
const tags = computed(() => page.data.value?.tags ?? [])

// ---- 编辑表单 ------------------------------------------------------------
const editing = ref<SoftwareEntry | null>(null)
const formOpen = ref(false)
const form = ref<Partial<SoftwareEntry>>({})
const tagsText = ref('')
const saving = ref(false)
const pendingRemove = ref<SoftwareEntry | null>(null)

// ---- 图片图标 -------------------------------------------------------------
const iconInput = ref<HTMLInputElement | null>(null)
const uploadingIcon = ref(false)

function pickIconFile() {
  iconInput.value?.click()
}

async function onIconFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选择同一个文件
  if (!file) return
  if (file.size > 2 * 1024 * 1024) {
    pushToast('图片超过 2MB，请压缩后再上传', 'warning')
    return
  }
  uploadingIcon.value = true
  try {
    const { url } = await api.uploadIcon(file)
    form.value.icon_image = url
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    uploadingIcon.value = false
  }
}

function removeIconImage() {
  form.value.icon_image = ''
}

function openCreate() {
  form.value = {
    name: '',
    url: '',
    description: '',
    category: '',
    tags: [],
    color: '',
    icon: '',
    icon_image: '',
  }
  tagsText.value = ''
  editing.value = null
  formOpen.value = true
}

function openEdit(entry: SoftwareEntry) {
  form.value = { ...entry, icon_image: entry.icon_image ?? '', tags: [...entry.tags] }
  tagsText.value = entry.tags.join(', ')
  editing.value = entry
  formOpen.value = true
}

function parseTags(input: string): string[] {
  return input
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

async function save() {
  if (!form.value.name?.trim()) {
    pushToast('名称不能为空', 'warning')
    return
  }
  saving.value = true
  try {
    // 地址统一补齐协议：`nas:8096` 这类值当作相对路径会跳回面板本身。
    const payload = {
      ...form.value,
      url: normalizeUrl(form.value.url),
      tags: parseTags(tagsText.value),
    }
    if (editing.value) {
      await api.updateEntry(editing.value.id, payload)
      pushToast('已更新', 'success')
    } else {
      await api.createEntry(payload)
      pushToast('已创建', 'success')
    }
    formOpen.value = false
    await page.refresh()
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}

async function confirmRemove() {
  const target = pendingRemove.value
  if (!target) return
  try {
    await api.deleteEntry(target.id)
    pushToast('已删除', 'success')
    await page.refresh()
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    pendingRemove.value = null
  }
}

function toggleTag(tag: string) {
  selectedTags.value = selectedTags.value.includes(tag)
    ? selectedTags.value.filter((t) => t !== tag)
    : [...selectedTags.value, tag]
}
</script>

<template>
  <section>
    <header class="catalog__bar">
      <input v-model="search" class="input catalog__search" placeholder="搜索名称或描述…" />
      <select v-model="sort" class="select">
        <option value="order">自定义排序</option>
        <option value="name">按名称</option>
        <option value="recent">按添加时间</option>
      </select>
      <span class="spacer" />
      <span class="dim">{{ page.data.value?.total ?? 0 }} 项</span>
      <button class="btn btn--primary" @click="openCreate">+ 新增软件</button>
    </header>

    <TagFilter
      :tags="tags"
      :selected="selectedTags"
      :match-all="matchAll"
      class="catalog__tags"
      @toggle="toggleTag"
      @update:match-all="matchAll = $event"
      @clear="selectedTags = []"
    />

    <div v-if="entries.length" class="catalog__grid">
      <SoftwareCard
        v-for="entry in entries"
        :key="entry.id"
        :entry="entry"
        :active-tags="selectedTags"
        @tag="toggleTag"
        @edit="openEdit"
        @remove="pendingRemove = $event"
      />
    </div>
    <EmptyState
      v-else
      title="没有匹配的软件"
      description="调整标签或搜索条件，或新增一个软件条目。"
    />

    <!-- 编辑/新增 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="formOpen" class="mask" @click.self="formOpen = false">
          <form class="editor card" @submit.prevent="save">
            <h3 class="editor__title">{{ editing ? '编辑软件' : '新增软件' }}</h3>
            <div class="editor__grid">
              <label class="field">
                <span class="field__label">名称 *</span>
                <input v-model="form.name" class="input" placeholder="例如 Jellyfin" />
              </label>
              <label class="field">
                <span class="field__label">地址</span>
                <input v-model="form.url" class="input" placeholder="http://host:8096" />
              </label>
              <label class="field editor__full">
                <span class="field__label">描述</span>
                <input v-model="form.description" class="input" placeholder="一句话说明" />
              </label>
              <label class="field">
                <span class="field__label">分类</span>
                <input v-model="form.category" class="input" placeholder="影音" />
              </label>
              <label class="field">
                <span class="field__label">标签（逗号分隔）</span>
                <input v-model="tagsText" class="input" placeholder="影音, 自建" />
              </label>
              <label class="field">
                <span class="field__label">主题色</span>
                <input v-model="form.color" class="input" placeholder="#4c8dff 或留空自动" />
              </label>
              <div class="field editor__full">
                <span class="field__label">图片图标</span>
                <div class="icon-picker">
                  <span
                    class="icon-picker__preview"
                    :style="form.icon_image ? { background: 'transparent' } : { background: form.color || colorFromString(form.name ?? '') }"
                  >
                    <img v-if="form.icon_image" :src="form.icon_image" alt="" />
                    <template v-else>{{ form.icon?.trim() || form.name?.charAt(0) || '？' }}</template>
                  </span>
                  <input
                    ref="iconInput"
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    hidden
                    @change="onIconFile"
                  />
                  <button
                    type="button"
                    class="btn btn--sm"
                    :disabled="uploadingIcon"
                    @click="pickIconFile"
                  >
                    {{ uploadingIcon ? '上传中…' : '上传图片' }}
                  </button>
                  <button
                    v-if="form.icon_image"
                    type="button"
                    class="btn btn--ghost btn--sm"
                    @click="removeIconImage"
                  >
                    移除
                  </button>
                  <span class="dim icon-picker__hint">PNG / JPEG / WebP / GIF，≤2MB</span>
                </div>
              </div>
              <label class="field">
                <span class="field__label">图标字符（无图片时显示）</span>
                <input v-model="form.icon" class="input" placeholder="🎬" />
              </label>
            </div>
            <footer class="editor__foot">
              <span class="spacer" />
              <button type="button" class="btn" @click="formOpen = false">取消</button>
              <button type="submit" class="btn btn--primary" :disabled="saving">
                {{ saving ? '保存中…' : '保存' }}
              </button>
            </footer>
          </form>
        </div>
      </Transition>
    </Teleport>

    <ConfirmDialog
      :open="!!pendingRemove"
      title="删除软件条目"
      :message="`确定删除「${pendingRemove?.name ?? ''}」？此操作不可撤销。`"
      danger
      confirm-text="删除"
      @cancel="pendingRemove = null"
      @confirm="confirmRemove"
    />
  </section>
</template>

<style scoped>
.catalog__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.catalog__search {
  width: min(300px, 50vw);
}

.catalog__tags {
  margin-bottom: 16px;
}

.catalog__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
}

.editor {
  width: min(560px, 94vw);
  padding: 20px;
  box-shadow: var(--shadow);
}

.editor__title {
  margin-bottom: 14px;
  font-size: 15px;
}

.editor__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.editor__full {
  grid-column: 1 / -1;
}

.editor__foot {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.icon-picker {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.icon-picker__preview {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
  color: #fff;
  font-weight: 600;
  font-size: 15px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}

.icon-picker__preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.icon-picker__hint {
  font-size: 12px;
}
</style>
