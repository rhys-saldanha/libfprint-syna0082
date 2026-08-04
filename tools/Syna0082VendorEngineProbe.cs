using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;

internal static class Syna0082VendorEngineProbe
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibrary(string path);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr module, string name);

    [DllImport("kernel32.dll")]
    private static extern bool FreeLibrary(IntPtr module);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetProcessHeap();

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool HeapFree(IntPtr heap, uint flags, IntPtr memory);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate int QueryEngineInterface(out IntPtr engineInterface);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate int EngineAttach(IntPtr pipeline);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate int EngineDetach(IntPtr pipeline);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate int EngineAcceptSampleData(
        IntPtr pipeline,
        IntPtr sampleBuffer,
        UIntPtr sampleSize,
        byte purpose,
        IntPtr rejectDetail);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate int EngineExportEngineData(
        IntPtr pipeline,
        byte flags,
        out IntPtr sampleBuffer,
        out UIntPtr sampleSize);

    private const int PipelineSize = 80;
    private const int EngineInterfaceOffset = 32;
    private const int EngineContextOffset = 56;
    private const int EngineTestModeOffset = 0x8c;
    private const int BirHeaderOffset = 0x20;
    private const int AnsiDataOffset = 0x50;
    private const int PixelOffset = 0x88;
    private const byte PurposeEnroll = 0x04;
    private const byte DataFlagIntermediate = 0x40;
    private const byte DataFlagProcessed = 0x80;

    private sealed class PgmImage
    {
        public int Width;
        public int Height;
        public byte[] Pixels;
    }

    private static string HResult(int value)
    {
        return "0x" + unchecked((uint)value).ToString("X8", CultureInfo.InvariantCulture);
    }

    private static T Function<T>(IntPtr pointer) where T : class
    {
        return (T)(object)Marshal.GetDelegateForFunctionPointer(pointer, typeof(T));
    }

    private static uint ReadUInt32(byte[] bytes, int offset)
    {
        return BitConverter.ToUInt32(bytes, offset);
    }

    private static void WriteUInt16(byte[] bytes, int offset, ushort value)
    {
        byte[] encoded = BitConverter.GetBytes(value);
        Buffer.BlockCopy(encoded, 0, bytes, offset, encoded.Length);
    }

    private static void WriteUInt32(byte[] bytes, int offset, uint value)
    {
        byte[] encoded = BitConverter.GetBytes(value);
        Buffer.BlockCopy(encoded, 0, bytes, offset, encoded.Length);
    }

    private static void WriteUInt64(byte[] bytes, int offset, ulong value)
    {
        byte[] encoded = BitConverter.GetBytes(value);
        Buffer.BlockCopy(encoded, 0, bytes, offset, encoded.Length);
    }

    private static string ReadPgmToken(byte[] bytes, ref int offset)
    {
        while (offset < bytes.Length)
        {
            if (bytes[offset] == '#')
            {
                while (offset < bytes.Length && bytes[offset] != '\n')
                    offset++;
            }
            else if (bytes[offset] <= 0x20)
            {
                offset++;
            }
            else
            {
                break;
            }
        }

        int start = offset;
        while (offset < bytes.Length && bytes[offset] > 0x20 && bytes[offset] != '#')
            offset++;
        return System.Text.Encoding.ASCII.GetString(bytes, start, offset - start);
    }

    private static PgmImage ReadPgm(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);
        int offset = 0;
        string magic = ReadPgmToken(bytes, ref offset);
        int width = int.Parse(ReadPgmToken(bytes, ref offset), CultureInfo.InvariantCulture);
        int height = int.Parse(ReadPgmToken(bytes, ref offset), CultureInfo.InvariantCulture);
        int maximum = int.Parse(ReadPgmToken(bytes, ref offset), CultureInfo.InvariantCulture);
        if (magic != "P5" || maximum != 255)
            throw new InvalidDataException("Only 8-bit binary PGM (P5) images are supported");
        while (offset < bytes.Length && bytes[offset] <= 0x20)
            offset++;
        int length = checked(width * height);
        if (bytes.Length - offset != length)
            throw new InvalidDataException("PGM payload size does not match its dimensions");
        byte[] pixels = new byte[length];
        Buffer.BlockCopy(bytes, offset, pixels, 0, length);
        return new PgmImage { Width = width, Height = height, Pixels = pixels };
    }

    // Build the exact ANSI-381 layout consumed by CBirFormaterAnsi in
    // synaBscAdapter52.dll. The vendor parser requires a 0x20 BIR root, a
    // header at 0x20, ANSI metadata at 0x50, and pixels at 0x88.
    private static byte[] BuildBir(PgmImage image)
    {
        if (image.Width <= 0 || image.Width >= 281 || image.Height <= 0 || image.Height >= 404)
            throw new InvalidDataException("Vendor engine dimensions are out of range");

        byte[] bir = new byte[PixelOffset + image.Pixels.Length];

        WriteUInt32(bir, 0x00, 0x30);             // HeaderBlock.Size
        WriteUInt32(bir, 0x04, BirHeaderOffset);  // HeaderBlock.Offset
        WriteUInt32(bir, 0x08, 0x38);             // vendor-required ANSI metadata size
        WriteUInt32(bir, 0x0c, AnsiDataOffset);   // StandardDataBlock.Offset

        bir[BirHeaderOffset + 2] = 0x11;          // CBEFF header version
        bir[BirHeaderOffset + 3] = 0x11;          // patron header version
        bir[BirHeaderOffset + 4] = 0x28;          // RAW | OPTION_MASK_PRESENT
        WriteUInt32(bir, BirHeaderOffset + 8, 0x08); // WINBIO_TYPE_FINGERPRINT
        bir[BirHeaderOffset + 12] = 0x02;         // right index finger
        bir[BirHeaderOffset + 13] = PurposeEnroll;
        bir[BirHeaderOffset + 14] = 0xff;         // quality not set
        WriteUInt16(bir, BirHeaderOffset + 40, 0x001b);
        WriteUInt16(bir, BirHeaderOffset + 42, 0x0401);

        WriteUInt64(bir, AnsiDataOffset + 0, (ulong)(0x38 + image.Pixels.Length));
        WriteUInt32(bir, AnsiDataOffset + 8, 0x46495200);
        WriteUInt32(bir, AnsiDataOffset + 12, 0x30313000);
        WriteUInt16(bir, AnsiDataOffset + 16, 0x001b);
        WriteUInt16(bir, AnsiDataOffset + 18, 0x0401);
        WriteUInt16(bir, AnsiDataOffset + 24, 197); // about 500 dpi, pixels/cm
        WriteUInt16(bir, AnsiDataOffset + 26, 197);
        WriteUInt16(bir, AnsiDataOffset + 28, 197);
        WriteUInt16(bir, AnsiDataOffset + 30, 197);
        bir[AnsiDataOffset + 32] = 1;             // one view
        bir[AnsiDataOffset + 33] = 2;             // centimeters
        bir[AnsiDataOffset + 34] = 8;             // bits per pixel
        bir[AnsiDataOffset + 35] = 0;             // uncompressed

        int record = AnsiDataOffset + 0x28;
        WriteUInt32(bir, record + 0, (uint)(0x10 + image.Pixels.Length));
        WriteUInt16(bir, record + 4, (ushort)image.Width);
        WriteUInt16(bir, record + 6, (ushort)image.Height);
        bir[record + 8] = 0x02;                   // right index finger
        bir[record + 9] = 1;                     // one view
        bir[record + 10] = 0;                    // view number
        bir[record + 11] = 100;                  // image quality
        bir[record + 12] = 0;                    // live-scan plain impression
        Buffer.BlockCopy(image.Pixels, 0, bir, PixelOffset, image.Pixels.Length);
        return bir;
    }

    private static IDictionary<string, string> ParseArguments(string[] args)
    {
        Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int index = 0; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length || !args[index].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException("Arguments must be --adapter PATH --image PATH [--output PATH]");
            values[args[index].Substring(2)] = args[index + 1];
        }
        return values;
    }

    public static int Main(string[] args)
    {
        IntPtr module = IntPtr.Zero;
        IntPtr pipeline = IntPtr.Zero;
        IntPtr birBuffer = IntPtr.Zero;
        bool attached = false;
        try
        {
            IDictionary<string, string> options = ParseArguments(args);
            string adapter = options["adapter"];
            string imagePath = options["image"];
            string outputPath = options.ContainsKey("output") ? options["output"] : null;
            PgmImage image = ReadPgm(imagePath);
            byte[] bir = BuildBir(image);

            module = LoadLibrary(adapter);
            if (module == IntPtr.Zero)
                throw new InvalidOperationException("LoadLibrary failed: " + Marshal.GetLastWin32Error());
            IntPtr queryAddress = GetProcAddress(module, "WbioQueryEngineInterface");
            if (queryAddress == IntPtr.Zero)
                throw new InvalidOperationException("WbioQueryEngineInterface was not found");
            QueryEngineInterface query = Function<QueryEngineInterface>(queryAddress);
            IntPtr engineInterface;
            int hr = query(out engineInterface);
            Console.WriteLine("query=" + HResult(hr));
            if (hr < 0)
                return 2;

            EngineAttach attach = Function<EngineAttach>(Marshal.ReadIntPtr(engineInterface, 32));
            EngineDetach detach = Function<EngineDetach>(Marshal.ReadIntPtr(engineInterface, 40));
            EngineAcceptSampleData accept = Function<EngineAcceptSampleData>(Marshal.ReadIntPtr(engineInterface, 96));
            EngineExportEngineData export = Function<EngineExportEngineData>(Marshal.ReadIntPtr(engineInterface, 104));

            pipeline = Marshal.AllocHGlobal(PipelineSize);
            for (int offset = 0; offset < PipelineSize; offset += 8)
                Marshal.WriteInt64(pipeline, offset, 0);
            Marshal.WriteInt64(pipeline, 0, -1);
            Marshal.WriteInt64(pipeline, 8, -1);
            Marshal.WriteInt64(pipeline, 16, -1);
            Marshal.WriteIntPtr(pipeline, EngineInterfaceOffset, engineInterface);

            hr = attach(pipeline);
            Console.WriteLine("attach=" + HResult(hr));
            if (hr < 0)
                return 3;
            attached = true;
            IntPtr engineContext = Marshal.ReadIntPtr(pipeline, EngineContextOffset);
            if (engineContext == IntPtr.Zero)
                throw new InvalidOperationException("Attach succeeded without an engine context");
            Console.WriteLine("engine-context=present");

            // The DLL normally enables this path only when hosted by biotest.exe.
            // It switches AcceptSampleData from the private 0x58 transport record
            // to the documented ANSI-381 BIR parser.
            Marshal.WriteInt32(engineContext, EngineTestModeOffset, 1);
            Console.WriteLine("test-mode=1");

            birBuffer = Marshal.AllocHGlobal(bir.Length);
            Marshal.Copy(bir, 0, birBuffer, bir.Length);
            IntPtr reject = Marshal.AllocHGlobal(4);
            try
            {
                Marshal.WriteInt32(reject, 0);
                Console.WriteLine("accept-start size=" + bir.Length);
                hr = accept(pipeline, birBuffer, new UIntPtr((uint)bir.Length), PurposeEnroll, reject);
                Console.WriteLine("accept=" + HResult(hr));
                Console.WriteLine("reject=" + Marshal.ReadInt32(reject));
                if (hr < 0)
                    return 4;
            }
            finally
            {
                Marshal.FreeHGlobal(reject);
            }

            byte[] exportFlags = { DataFlagIntermediate, DataFlagProcessed };
            foreach (byte flags in exportFlags)
            {
                IntPtr exported;
                UIntPtr exportedSize;
                hr = export(pipeline, flags, out exported, out exportedSize);
                Console.WriteLine("export-0x" + flags.ToString("X2") + "=" + HResult(hr));
                if (hr == 0 && exported != IntPtr.Zero)
                {
                    ulong length64 = exportedSize.ToUInt64();
                    Console.WriteLine("export-size=" + length64);
                    if (length64 > int.MaxValue)
                        throw new InvalidDataException("Exported feature set is unexpectedly large");
                    byte[] data = new byte[(int)length64];
                    Marshal.Copy(exported, data, 0, data.Length);
                    if (!String.IsNullOrEmpty(outputPath))
                    {
                        File.WriteAllBytes(outputPath, data);
                        Console.WriteLine("output=" + outputPath);
                    }
                    HeapFree(GetProcessHeap(), 0, exported);
                    return 0;
                }
            }
            return 5;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception.ToString());
            return 1;
        }
        finally
        {
            if (attached && pipeline != IntPtr.Zero)
            {
                try
                {
                    // Resolve Detach again only while the module is still loaded.
                    IntPtr queryAddress = GetProcAddress(module, "WbioQueryEngineInterface");
                    QueryEngineInterface query = Function<QueryEngineInterface>(queryAddress);
                    IntPtr engineInterface;
                    if (query(out engineInterface) == 0)
                        Function<EngineDetach>(Marshal.ReadIntPtr(engineInterface, 40))(pipeline);
                }
                catch
                {
                }
            }
            if (birBuffer != IntPtr.Zero)
                Marshal.FreeHGlobal(birBuffer);
            if (pipeline != IntPtr.Zero)
                Marshal.FreeHGlobal(pipeline);
            if (module != IntPtr.Zero)
                FreeLibrary(module);
        }
    }
}
