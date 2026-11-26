extern void *dlopen(const char *, int);
extern void *dlsym(void *, const char *);
extern void *dlvsym(void *, const char *, const char *);
extern char *dlerror(void);
extern long write(int, const void *, unsigned long);
extern void _exit(int) __attribute__((noreturn));

static void emit(const char *text)
{
    unsigned long length = 0;
    while (text[length])
        ++length;
    write(1, text, length);
}

static void probe(void *handle, const char *name, const char *version)
{
    void *address = version ? dlvsym(handle, name, version) : dlsym(handle, name);
    emit(address ? "FOUND " : "ABSENT ");
    emit(name);
    if (version) {
        emit("@");
        emit(version);
    }
    emit("\n");
}

static void *open_library(const char *path)
{
    void *handle = dlopen(path, 2); /* RTLD_NOW */
    if (!handle) {
        emit("LOAD_ERROR ");
        emit(path);
        emit(": ");
        emit(dlerror());
        emit("\n");
        _exit(1);
    }
    return handle;
}

void _start(void)
{
    void *solv = open_library("/audit/libsolv.so.1");
    probe(solv, "pool_create", "SOLV_1.0");
    probe(solv, "pool_best_solvables", "SOLV_1.1");
    probe(solv, "selection_subtract", "SOLV_1.2");
    probe(solv, "repodata_set_kv", "SOLV_1.3");

    void *installer = open_library("/audit/libapp-installers.so.1");
    probe(installer, "_ZN16common_installer12AppInstallerC1EPKcSt10shared_ptrINS_15PkgMgrInterfaceEE", 0);
    probe(installer, "_ZN16common_installer6PluginC1ERKNS_10PluginInfoE", 0);
    probe(installer, "_ZN16common_installer8security27StepCheckBackgroundCategoryC1EPNS_16InstallerContextE", 0);
    _exit(0);
}
