// Dump selected functions from a Ghidra headless project as decompiled C.
// @category Analysis

import java.io.File;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DumpNamedFunctions extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "usage: DumpNamedFunctions.java OUTPUT ADDRESS [ADDRESS ...]");
        }

        File output = new File(args[0]);
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        try (PrintWriter writer = new PrintWriter(output, "UTF-8")) {
            for (int index = 1; index < args.length; index++) {
                Address address = currentProgram.getAddressFactory().getAddress(args[index]);
                if (address == null) {
                    writer.println("/* Invalid address: " + args[index] + " */");
                    continue;
                }
                Function function = currentProgram.getFunctionManager()
                    .getFunctionContaining(address);
                if (function == null) {
                    writer.println("/* No function contains " + address + " */");
                    continue;
                }

                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                writer.println("/* " + function.getName() + " @ " +
                    function.getEntryPoint() + " */");
                if (!result.decompileCompleted()) {
                    writer.println("/* Decompilation failed: " +
                        result.getErrorMessage() + " */");
                } else {
                    writer.println(result.getDecompiledFunction().getC());
                }
            }
        } finally {
            decompiler.dispose();
        }
    }
}
