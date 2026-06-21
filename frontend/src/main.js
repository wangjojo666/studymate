import { createApp } from "vue";
import {
  ElAlert,
  ElAside,
  ElButton,
  ElContainer,
  ElDatePicker,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElHeader,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElLoading,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElProgress,
  ElSelect,
  ElSkeleton,
  ElSwitch,
  ElTabPane,
  ElTabs,
  ElTag,
  ElUpload
} from "element-plus";
import "element-plus/es/components/alert/style/css";
import "element-plus/es/components/aside/style/css";
import "element-plus/es/components/button/style/css";
import "element-plus/es/components/container/style/css";
import "element-plus/es/components/date-picker/style/css";
import "element-plus/es/components/dialog/style/css";
import "element-plus/es/components/drawer/style/css";
import "element-plus/es/components/empty/style/css";
import "element-plus/es/components/form/style/css";
import "element-plus/es/components/form-item/style/css";
import "element-plus/es/components/header/style/css";
import "element-plus/es/components/icon/style/css";
import "element-plus/es/components/input/style/css";
import "element-plus/es/components/input-number/style/css";
import "element-plus/es/components/loading/style/css";
import "element-plus/es/components/main/style/css";
import "element-plus/es/components/menu/style/css";
import "element-plus/es/components/menu-item/style/css";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import "element-plus/es/components/option/style/css";
import "element-plus/es/components/progress/style/css";
import "element-plus/es/components/select/style/css";
import "element-plus/es/components/skeleton/style/css";
import "element-plus/es/components/switch/style/css";
import "element-plus/es/components/tab-pane/style/css";
import "element-plus/es/components/tabs/style/css";
import "element-plus/es/components/tag/style/css";
import "element-plus/es/components/upload/style/css";
import {
  ArrowRight,
  Back,
  Calendar,
  ChatLineRound,
  CircleCheck,
  Collection,
  CopyDocument,
  Cpu,
  DataAnalysis,
  Document,
  Download,
  EditPen,
  FolderOpened,
  House,
  Memo,
  Notebook,
  Plus,
  Promotion,
  Reading,
  Refresh,
  Right,
  Setting,
  Upload
} from "@element-plus/icons-vue";

import App from "./App.vue";
import router from "./router";
import "./styles.css";

const app = createApp(App);

const elementComponents = [
  ElAlert,
  ElAside,
  ElButton,
  ElContainer,
  ElDatePicker,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElHeader,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElProgress,
  ElSelect,
  ElSkeleton,
  ElSwitch,
  ElTabPane,
  ElTabs,
  ElTag,
  ElUpload
];

const icons = {
  ArrowRight,
  Back,
  Calendar,
  ChatLineRound,
  CircleCheck,
  Collection,
  CopyDocument,
  Cpu,
  DataAnalysis,
  Document,
  Download,
  EditPen,
  FolderOpened,
  House,
  Memo,
  Notebook,
  Plus,
  Promotion,
  Reading,
  Refresh,
  Right,
  Setting,
  Upload
};

for (const component of elementComponents) {
  app.use(component);
}

for (const [key, component] of Object.entries(icons)) {
  app.component(key, component);
}

app.use(ElLoading);
app.use(router);
app.mount("#app");
