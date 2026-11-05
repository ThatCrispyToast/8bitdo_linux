// Decompile all named (exported / non-FUN_) functions plus callees (BFS), following thunks.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import java.io.*;
import java.util.*;

public class DecompExports extends GhidraScript {
    FunctionManager fm;
    Listing listing;

    Function resolve(Address a) {
        if (a == null) return null;
        Function f = fm.getFunctionAt(a);
        if (f == null) {
            // maybe an ILT jmp stub without a function: follow one unconditional jump
            Instruction ins = listing.getInstructionAt(a);
            if (ins != null && ins.getFlowType().isJump() && !ins.getFlowType().isConditional()) {
                Address[] flows = ins.getFlows();
                if (flows.length == 1) f = fm.getFunctionAt(flows[0]);
            }
            if (f == null) f = fm.getFunctionContaining(a);
        }
        int guard = 0;
        while (f != null && f.isThunk() && guard++ < 8) {
            Function t = f.getThunkedFunction(false);
            if (t == null) break;
            f = t;
        }
        return f;
    }

    List<Function> callees(Function f) {
        List<Function> out = new ArrayList<>();
        InstructionIterator it = listing.getInstructions(f.getBody(), true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            if (!ins.getFlowType().isCall()) continue;
            for (Address a : ins.getFlows()) {
                Function c = resolve(a);
                if (c != null && !c.isExternal()) out.add(c);
            }
        }
        return out;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        int maxDepth = args.length > 1 ? Integer.parseInt(args[1]) : 3;
        int maxFuncs = args.length > 2 ? Integer.parseInt(args[2]) : 1500;
        fm = currentProgram.getFunctionManager();
        listing = currentProgram.getListing();
        SymbolTable st = currentProgram.getSymbolTable();
        LinkedHashMap<Function,Integer> todo = new LinkedHashMap<>();
        AddressIterator it = st.getExternalEntryPointIterator();
        while (it.hasNext()) {
            Function f = resolve(it.next());
            if (f != null && !f.isExternal()) todo.put(f, 0);
        }
        println("seed exports (thunks resolved): " + todo.size());
        if (System.getenv("SEED_NAMED") != null)
        for (Function f : fm.getFunctions(true)) {
            if (f.isExternal() || f.isThunk()) continue;
            String n = f.getName();
            if (n.startsWith("FUN_") || n.startsWith("thunk_") || n.startsWith("Catch@") || n.startsWith("Unwind@")) continue;
            if (n.startsWith("__") || n.startsWith("_RTC") || n.startsWith("?")) continue; // CRT / mangled C++
            if (!todo.containsKey(f)) todo.put(f, 0);
        }
        println("seeds incl. named functions: " + todo.size());
        ArrayDeque<Function> q = new ArrayDeque<>(todo.keySet());
        while (!q.isEmpty() && todo.size() < maxFuncs) {
            Function f = q.poll();
            int d = todo.get(f);
            if (d >= maxDepth) continue;
            for (Function c : callees(f)) {
                if (!todo.containsKey(c)) { todo.put(c, d+1); q.add(c); }
            }
        }
        println("total to decompile: " + todo.size());
        DecompInterface ifc = new DecompInterface();
        ifc.setOptions(new DecompileOptions());
        ifc.openProgram(currentProgram);
        try (PrintWriter pw = new PrintWriter(new FileWriter(outPath))) {
            int n = 0;
            for (Map.Entry<Function,Integer> e : todo.entrySet()) {
                Function f = e.getKey();
                monitor.checkCancelled();
                pw.println("// ==================== " + f.getName() + " @ " + f.getEntryPoint() + " depth=" + e.getValue() + " ====================");
                DecompileResults r = ifc.decompileFunction(f, 120, monitor);
                if (r != null && r.decompileCompleted()) pw.println(r.getDecompiledFunction().getC());
                else pw.println("// DECOMPILE FAILED: " + (r == null ? "null" : r.getErrorMessage()));
                pw.flush();
                if (++n % 100 == 0) println("decompiled " + n + "/" + todo.size());
            }
        }
        ifc.dispose();
        println("done -> " + outPath);
    }
}
