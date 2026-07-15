<script setup lang="ts">
import { getMine } from "@/api/user";
import { useRouter } from "vue-router";
import Profile from "./components/Profile.vue";
import { ref, onMounted, onBeforeMount } from "vue";
import { useUserStoreHook } from "@/store/modules/user";
import { avatarDataUri } from "@/utils/avatar";
import { useGlobal, deviceDetection } from "@pureadmin/utils";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import LaySidebarTopCollapse from "@/layout/components/lay-sidebar/components/SidebarTopCollapse.vue";
import IconifyIconOffline from "@/components/ReIcon/src/iconifyIconOffline";
import leftLine from "~icons/ri/arrow-left-s-line";

defineOptions({ name: "AccountSettings" });

const router = useRouter();
const isOpen = ref(deviceDetection() ? false : true);
const { $storage } = useGlobal<GlobalPropertiesApi>();
onBeforeMount(() => {
  useDataThemeChange().dataThemeChange($storage.layout?.themeMode);
});

const userInfo = ref({ avatar: "", username: "", nickname: "" });

onMounted(async () => {
  const store = useUserStoreHook();
  try {
    const { code, data } = await getMine();
    if (code === 200) {
      userInfo.value = {
        avatar: data.avatar || avatarDataUri(data.username || "U", data.nickname),
        username: data.username || store.username || "",
        nickname: data.nickname || store.nickname || data.username || ""
      };
    }
  } catch {
    userInfo.value = {
      avatar: avatarDataUri(store.username || "U", store.nickname),
      username: store.username || "",
      nickname: store.nickname || store.username || ""
    };
  }
});
</script>

<template>
  <el-container class="h-full">
    <el-aside
      v-if="isOpen"
      class="pure-account-settings overflow-hidden px-2 dark:bg-(--el-bg-color)! border-r border-(--pure-border-color)"
      :width="deviceDetection() ? '180px' : '240px'"
    >
      <div class="pure-account-settings-menu">
        <div
          class="h-12.5! text-(--pure-theme-menu-text) cursor-pointer text-sm transition-all duration-300 ease-in-out hover:scale-105 will-change-transform transform-gpu origin-center hover:text-base! hover:text-(--pure-theme-menu-title-hover)!"
          @click="router.go(-1)"
        >
          <div class="h-full flex items-center px-(--el-menu-base-level-padding)">
            <IconifyIconOffline :icon="leftLine" />
            <span class="ml-2">返回</span>
          </div>
        </div>
        <div class="flex items-center px-4 py-4">
          <el-avatar :size="48" :src="userInfo.avatar" />
          <div class="ml-4 flex flex-col min-w-0">
            <span class="font-bold text-sm truncate">{{ userInfo.nickname }}</span>
            <span class="text-xs text-slate-400 truncate">{{ userInfo.username }}</span>
          </div>
        </div>
      </div>
    </el-aside>
    <el-main class="p-0!">
      <LaySidebarTopCollapse
        v-if="deviceDetection()"
        class="px-0"
        :is-active="isOpen"
        @toggleClick="isOpen = !isOpen"
      />
      <Profile />
    </el-main>
  </el-container>
</template>

<style lang="scss">
.pure-account-settings {
  background: var(--pure-theme-menu-bg) !important;
}

.pure-account-settings-menu {
  background-color: transparent;
  border: none;
}
</style>

<style lang="scss" scoped>
body[layout] {
  .el-menu--vertical .is-active {
    color: #fff !important;
    transition: color 0.2s;
    &:hover { color: #fff !important; }
  }
}
</style>
